from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend


def b64url_no_padding(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    private_number = private_key.private_numbers().private_value
    public_numbers = private_key.public_key().public_numbers()

    private_key_text = b64url_no_padding(private_number.to_bytes(32, "big"))
    public_key_text = b64url_no_padding(
        b"\x04"
        + public_numbers.x.to_bytes(32, "big")
        + public_numbers.y.to_bytes(32, "big")
    )

    print("[push]")
    print(f'vapid_public_key = "{public_key_text}"')
    print(f'vapid_private_key = "{private_key_text}"')
    print('vapid_subject = "mailto:your-email@example.com"')


if __name__ == "__main__":
    main()
