"""Application-level push notification hooks."""
from __future__ import annotations

import copy
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Callable, Mapping, Protocol

from src.db.persistence import Persistence
from src.db.persistence_helpers import normalize_email
from src.assistant.stories.information import record_goal_invitation_news

from .sender import push_configured, send_push_to_user
from .storage import PushStorage


MIN_ACTIVE_GOALS_FOR_INVITATION_NOTIFICATIONS = 3
INVITATION_NOTIFICATION_ACCOUNT_AGE = timedelta(weeks=2)
GOAL_NOTIFICATION_WORKERS = 4
GOAL_NOTIFICATION_PENDING_JOBS = 100

logger = logging.getLogger(__name__)


class NotificationDispatcher(Protocol):
    """Submit best-effort notification work without blocking the caller."""

    def submit(self, key: str, task: Callable[[], None]) -> bool: ...


class InlineNotificationDispatcher:
    """Deterministic dispatcher for tests and command-line callers."""

    def submit(self, key: str, task: Callable[[], None]) -> bool:
        del key
        task()
        return True


class ThreadedNotificationDispatcher:
    """Bounded, process-local executor for best-effort push delivery."""

    def __init__(
        self,
        *,
        max_workers: int = GOAL_NOTIFICATION_WORKERS,
        max_pending_jobs: int = GOAL_NOTIFICATION_PENDING_JOBS,
    ) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="dogether-push",
        )
        self._capacity = threading.BoundedSemaphore(max_workers + max_pending_jobs)
        self._lock = threading.Lock()
        self._active_keys: set[str] = set()

    def submit(self, key: str, task: Callable[[], None]) -> bool:
        with self._lock:
            if key in self._active_keys:
                return True
            if not self._capacity.acquire(blocking=False):
                logger.warning("goal_notification_queue_full key=%s", key)
                return False
            self._active_keys.add(key)

        def run() -> None:
            started_at = monotonic()
            try:
                task()
            except Exception:
                logger.exception("goal_notification_failed key=%s", key)
            finally:
                duration_ms = (monotonic() - started_at) * 1000
                logger.info(
                    "goal_notification_finished key=%s duration_ms=%.1f",
                    key,
                    duration_ms,
                )
                with self._lock:
                    self._active_keys.discard(key)
                self._capacity.release()

        try:
            self._executor.submit(run)
        except Exception:
            with self._lock:
                self._active_keys.discard(key)
            self._capacity.release()
            logger.exception("goal_notification_submit_failed key=%s", key)
            return False
        return True

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


_notification_dispatcher: ThreadedNotificationDispatcher | None = None
_notification_dispatcher_lock = threading.Lock()


def get_notification_dispatcher() -> ThreadedNotificationDispatcher:
    global _notification_dispatcher
    with _notification_dispatcher_lock:
        if _notification_dispatcher is None:
            _notification_dispatcher = ThreadedNotificationDispatcher()
        return _notification_dispatcher


def _display_name(user: Mapping[str, Any]) -> str:
    return str(user.get("name") or user.get("email") or "A friend")


def create_goal_with_invitation_news(
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    *,
    created_by: str,
    description: str,
    schedule_class: str,
    required_periods: int,
    friend_user_ids: list[str],
    target: int,
    current: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    goal = persistence.create_goal(
        created_by, description, schedule_class, required_periods, friend_user_ids, target, current, now
    )
    _announce_goal_invitations(persistence, push_storage, push_settings, goal, created_by, friend_user_ids, now=now)
    return goal


def add_goal_friends_with_invitation_news(
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    *,
    goal_id: str,
    user_id: str,
    friend_user_ids: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    before = persistence.list_goals_for_user(user_id, now=now)
    before_goal = next((goal for goal in before if goal.get("id") == goal_id), {})
    before_participants = set(before_goal.get("participants", {}))
    goal = persistence.add_goal_friends(goal_id, user_id, friend_user_ids, now=now)
    recipients = [participant_id for participant_id in goal.get("participants", {}) if participant_id not in before_participants]
    _announce_goal_invitations(persistence, push_storage, push_settings, goal, user_id, recipients, now=now)
    return goal


def _announce_goal_invitations(
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    goal: Mapping[str, Any],
    inviter_user_id: str,
    recipient_user_ids: list[str],
    *,
    now: datetime | None,
) -> None:
    inviter = persistence.get_user(inviter_user_id) or {}
    inviter_name = _display_name(inviter)
    recipients = sorted({user_id for user_id in recipient_user_ids if user_id != inviter_user_id})
    eligible_recipients = []
    age_unlocked_recipient_ids = []
    star_reward_recipient_ids = []
    for recipient_user_id in recipients:
        profile = persistence.get_user(recipient_user_id) or {}
        reached_goal_threshold = (
            len(persistence.list_goals_for_user(recipient_user_id, now=now))
            >= MIN_ACTIVE_GOALS_FOR_INVITATION_NOTIFICATIONS
        )
        reached_account_age_threshold = _account_is_older_than_invitation_grace_period(profile, now)
        if not (reached_goal_threshold or reached_account_age_threshold):
            continue
        eligible_recipients.append(recipient_user_id)
        if reached_goal_threshold:
            star_reward_recipient_ids.append(recipient_user_id)
        if reached_account_age_threshold and not reached_goal_threshold:
            age_unlocked_recipient_ids.append(recipient_user_id)

    if not eligible_recipients:
        return

    record_goal_invitation_news(
        persistence,
        eligible_recipients,
        goal=goal,
        inviter_name=inviter_name,
        mark_notifications_unlocked_recipient_ids=age_unlocked_recipient_ids,
        award_star_recipient_ids=star_reward_recipient_ids,
        now=now,
    )
    if not push_storage or not push_configured(push_settings):
        return
    for recipient_user_id in eligible_recipients:
        send_push_to_user(
            push_storage, recipient_user_id,
            title="Assistant", body=f"{inviter_name} invited you to a new shared goal.", url="/",
            vapid_private_key=push_settings["vapid_private_key"], vapid_subject=push_settings["vapid_subject"],
        )


def _account_is_older_than_invitation_grace_period(
    profile: Mapping[str, Any], now: datetime | None
) -> bool:
    created_at = profile.get("created_at")
    if not isinstance(created_at, str):
        return False
    try:
        created_at_dt = datetime.fromisoformat(created_at)
    except ValueError:
        return False
    if created_at_dt.tzinfo is None:
        return False

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    return current_time.astimezone(timezone.utc) > (
        created_at_dt.astimezone(timezone.utc) + INVITATION_NOTIFICATION_ACCOUNT_AGE
    )


def create_friend_invite_with_push(
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    *,
    from_user_id: str,
    from_email: str,
    to_email: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized_to_email = normalize_email(to_email)
    pending_before = {
        invite["id"]
        for invite in persistence.outgoing_friend_invites(from_user_id)
        if invite.get("to_email") == normalized_to_email
    }

    invite = persistence.create_friend_invite(from_user_id, from_email, to_email, now=now)
    if invite["id"] in pending_before:
        return invite

    recipient = persistence.find_user_by_email(normalized_to_email)
    if not recipient or not push_storage or not push_configured(push_settings):
        return invite

    send_push_to_user(
        push_storage,
        recipient["user_id"],
        title="New friend request",
        body="You have a new friend request in Dogether.",
        url="/",
        vapid_private_key=push_settings["vapid_private_key"],
        vapid_subject=push_settings["vapid_subject"],
    )
    return invite


def create_friend_suggestion_with_push(
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    *,
    suggested_by_user_id: str,
    suggested_user_ids: list[str],
    source_goal_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    suggested_pair = sorted(set(suggested_user_ids))
    pending_before = set()
    if len(suggested_pair) == 2:
        pending_before = {
            suggestion["id"]
            for suggestion in persistence.list_friend_suggestions_for_pair(*suggested_pair)
            if suggestion.get("status") == "pending"
        }

    suggestion = persistence.create_friend_suggestion(
        suggested_by_user_id,
        suggested_pair,
        source_goal_id=source_goal_id,
        now=now,
    )
    if suggestion["id"] in pending_before:
        return suggestion
    if not push_storage or not push_configured(push_settings):
        return suggestion

    users = persistence.users_by_ids([suggested_by_user_id, *suggestion["suggested_user_ids"]])
    suggester = users.get(suggested_by_user_id, {})
    suggester_name = suggester.get("name") or suggester.get("email") or "A friend"
    for recipient_id in suggestion["suggested_user_ids"]:
        other_id = next(
            user_id
            for user_id in suggestion["suggested_user_ids"]
            if user_id != recipient_id
        )
        other = users.get(other_id, {})
        other_name = other.get("name") or other.get("email") or "another friend"
        send_push_to_user(
            push_storage,
            recipient_id,
            title="New friend suggestion",
            body=f"{suggester_name} suggested you and {other_name} become friends in Dogether.",
            url="/",
            vapid_private_key=push_settings["vapid_private_key"],
            vapid_subject=push_settings["vapid_subject"],
        )
    return suggestion


def update_goal_progress_with_push(
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    *,
    goal_id: str,
    user_id: str,
    current: int | None = None,
    target: int | None = None,
    delta: int = 0,
    skipped: bool | None = None,
    now: datetime | None = None,
    dispatcher: NotificationDispatcher | None = None,
) -> dict[str, Any]:
    started_at = monotonic()
    goal = persistence.update_goal_progress(
        goal_id,
        user_id,
        current=current,
        target=target,
        delta=delta,
        skipped=skipped,
        now=now,
    )
    event = goal.get("_notification_event")
    if not event or not push_storage or not push_configured(push_settings):
        logger.info(
            "goal_progress_saved goal_id=%s duration_ms=%.1f notification_queued=false",
            goal_id,
            (monotonic() - started_at) * 1000,
        )
        return goal

    notification_day = str(event.get("day") or datetime.now().date().isoformat())
    notification_key = f"{goal_id}:{user_id}:{notification_day}"
    immutable_goal = copy.deepcopy(goal)
    immutable_settings = dict(push_settings)
    selected_dispatcher = (
        get_notification_dispatcher() if dispatcher is None else dispatcher
    )
    queued = selected_dispatcher.submit(
        notification_key,
        lambda: _send_goal_completion_notifications(
            persistence,
            push_storage,
            immutable_settings,
            immutable_goal,
            user_id,
            notification_day,
            now,
        ),
    )
    logger.info(
        "goal_progress_saved goal_id=%s duration_ms=%.1f notification_queued=%s",
        goal_id,
        (monotonic() - started_at) * 1000,
        str(queued).lower(),
    )
    return goal


def _send_goal_completion_notifications(
    persistence: Persistence,
    push_storage: PushStorage,
    push_settings: Mapping[str, str],
    goal: Mapping[str, Any],
    user_id: str,
    notification_day: str,
    now: datetime | None,
) -> None:

    friend_ids = {friend["user_id"] for friend in persistence.list_friends(user_id)}
    participant_ids = [
        participant_id
        for participant_id in goal.get("participant_user_ids", [])
        if participant_id != user_id
        and participant_id in friend_ids
        and not goal.get("participants", {}).get(participant_id, {}).get("left_at")
        and goal.get("participants", {}).get(participant_id, {}).get("completion_notifications_enabled", True)
    ]
    if not participant_ids:
        return

    users = persistence.users_by_ids([user_id, *participant_ids])
    completed_by = users.get(user_id, {}).get("name") or users.get(user_id, {}).get("email") or "A friend"
    description = str(goal.get("description") or "a shared goal")
    completed_participant = goal.get("participants", {}).get(user_id, {})
    current_value = max(0, int(completed_participant.get("current", 0)))
    target_value = max(1, int(completed_participant.get("target", 1)))

    for participant_id in participant_ids:
        if not persistence.claim_goal_completion_notification(goal["id"], participant_id, notification_day, now=now):
            continue
        result = send_push_to_user(
            push_storage,
            participant_id,
            title="Shared goal completed",
            body=f"{completed_by} completed {description}: {current_value} / {target_value}.",
            url="/",
            vapid_private_key=push_settings["vapid_private_key"],
            vapid_subject=push_settings["vapid_subject"],
        )
        if result.get("errors"):
            logger.warning(
                "goal_notification_delivery_errors goal_id=%s recipient_id=%s error_count=%d",
                goal["id"],
                participant_id,
                len(result["errors"]),
            )


def set_goal_completion_reaction_with_push(
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    *,
    goal_id: str,
    completed_user_id: str,
    reacting_user_id: str,
    emote: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    goal = persistence.set_goal_completion_reaction(
        goal_id,
        completed_user_id=completed_user_id,
        reacting_user_id=reacting_user_id,
        emote=emote,
        now=now,
    )
    if not str(emote).strip():
        return goal
    if not push_storage or not push_configured(push_settings):
        return goal
    participant = goal.get("participants", {}).get(completed_user_id, {})
    if not participant.get("reaction_notifications_enabled", True):
        return goal
    if not persistence.claim_goal_reaction_notification(goal_id, completed_user_id, reacting_user_id, now=now):
        return goal

    users = persistence.users_by_ids([reacting_user_id, completed_user_id])
    reacting_user = users.get(reacting_user_id, {})
    reacting_name = reacting_user.get("name") or reacting_user.get("email") or "A friend"
    description = str(goal.get("description") or "your goal")
    current = max(0, int(participant.get("current", 0) or 0))
    target = max(1, int(participant.get("target", 1) or 1))
    body = (
        f"{reacting_name} sent {emote} to your completion of “{description}”"
        if current >= target
        else f"{reacting_name} sent {emote} for “{description}”"
    )
    send_push_to_user(
        push_storage,
        completed_user_id,
        title="New goal reaction",
        body=body,
        url="/",
        vapid_private_key=push_settings["vapid_private_key"],
        vapid_subject=push_settings["vapid_subject"],
    )
    return goal
