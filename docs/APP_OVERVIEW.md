# Dogether app overview

Dogether is a Streamlit app that helps friends create, share, and track recurring goals together. It is designed around daily and weekly routines: participants set targets, record progress, see one another's activity, and celebrate completed goals.

This document is a product and contributor overview. For local setup, testing, persistence configuration, push notifications, debug tools, and deployment, see the [README](../README.md).

## Core experience

Users sign in with Google (or use the local debug-login flow during development), then connect with other users through email invitations or share links. Accepted friends can create shared goals with daily or weekly schedules, including variants that combine daily goals with weekly targets or weekly goals with monthly targets.

The app's main areas support that flow:

- **Goals** is the daily activity hub. It shows recent activity and active shared goals, lets a participant mark a goal done or adjust their progress, and displays each visible participant's progress, history, and completion reactions.
- **Friends** manages invitations, accepted friendships, and removals.
- **Manage Goals** creates shared goals, adds accepted friends to them, and lets a user leave a goal.
- **Historical Data Repair** corrects previous periods when progress was missed or entered incorrectly.
- **Account** presents profile details, completion statistics, and an activity history. Health Data Import and Push Notifications provide optional device-data and notification support.

Goal activity is stored per participant and period so the app can calculate completion history, streaks, summaries, and stats. Participants can react to another participant's completed goal, and supported events can generate web push notifications.

## The Goals page and assistant entry points

The Goals page is where a user normally returns to update their own progress and check in on their friends. It places the current user first, restricts visible participant details to the user and their accepted friends, and provides progress controls appropriate to the viewport.

The page also introduces the assistant in two situations:

- A user who has never started the tutorial can choose to write to the assistant or dismiss the offer.
- A user with pending shared-goal invitations sees an important-news card that can open the assistant or dismiss the news.

Both routes pass the user to the dedicated Assistant page. The assistant can also navigate a user back to Goals, Friends, Manage Goals, or Push Notifications when a story calls for it.

## Assistant story system

The Assistant is a scripted, NPC-like conversational experience, not a free-form or autonomous AI chat. Its stories use short messages, typing pauses, data-led cards, and button-led choices to guide a user through a focused interaction.

### Interaction style

The assistant should feel like a friendly NPC.

#### Rules

- One thought per message.
- Usually 2-10 words.
- Never more than ~18 words.
- Maximum 3-4 assistant bubbles before a choice.
- Choices are buttons.
- Fake typing between meaningful beats.
- Never ask open-ended questions when a button works.
- Use known user data directly.
- Never explain what it is checking.

For example, avoid:

> “I've analyzed your profile and noticed that you currently only have one friend, which may limit your experience.”

Instead:

> “I had a look.”
>
> typing…
>
> “You have one friend here.”
>
> “Let's fix that.”

[Invite someone] [Not now]


### Everyday assistance and playful smalltalk

For normal daily tasks, the Assistant should be friendly, clear, and helpful. It should help users track goals and understand what to do next without getting in the way.

The Assistant also has a smalltalk feature that is still being developed. In short interactive stories, it can be funny or a little strange. It can do things that normal apps and assistants usually do not do, such as wait in silence, act confused, or say that it wants to sleep. The greetings and night stories show this idea.

These playful moments should not make normal tasks harder. The Assistant should stay useful for everyday work, while smalltalk can offer an optional surprise.

Each story returns declarative turns. A turn can contain assistant messages and cards, selectable choices or a send control, status and progress feedback, navigation to another page, and requested state changes. `AssistantDirector` chooses the applicable story, advances its scene in response to a user selection or automatic transition, applies the turn's state updates, and hands presentation to the Streamlit view.

Assistant state is split by lifetime:

- **Durable per-user state** records completed progress and reusable context, including the current story/scene/status, knowledge flags, events, sequences, stars, and mode.
- **Session-scoped state** retains unfinished transitions, the visible transcript, the active control, and story-specific temporary values. This keeps an in-progress visit coherent without persisting UI mechanics as profile data.

The dispatcher prioritizes and resumes stories based on the user's state and current data. Current flows include:

- the initial tutorial and reusable feature explanations;
- goal-invitation information news;
- routine greetings and standard help;
- weekly-summary readiness and weekly insights;
- prompts to enable push notifications after eligible goal completions; and
- special or late-night experiences.

The Assistant page supplies each story with the user's friends, goals, completion count, notification status, and approved friend profiles. Stories can therefore acknowledge relevant app state and direct the user to the appropriate page without acting as an open-ended chat service.


