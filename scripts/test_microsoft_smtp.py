#!/usr/bin/env python3
"""Test Microsoft 365 SMTP AUTH from a local workstation."""

from __future__ import annotations

import argparse
import getpass
import os
import smtplib
import socket
import ssl
import sys
from datetime import datetime, timezone
from email.message import EmailMessage


DEFAULT_HOST = "smtp.office365.com"
DEFAULT_PORT = 587
DEFAULT_USERNAME = "cisco_api@space.gr"
DEFAULT_RECIPIENT = "nstam@space.gr"


def parse_args() -> argparse.Namespace:
    """Parse command line options."""
    parser = argparse.ArgumentParser(
        description=(
            "Send test mail through Microsoft 365 SMTP AUTH. The default test uses "
            "cisco_api@space.gr as the authenticated user and From address."
        )
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"SMTP host. Default: {DEFAULT_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"SMTP port. Default: {DEFAULT_PORT}")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help=f"SMTP username. Default: {DEFAULT_USERNAME}")
    parser.add_argument("--to", default=DEFAULT_RECIPIENT, help=f"Recipient address. Default: {DEFAULT_RECIPIENT}")
    parser.add_argument(
        "--from-email",
        default=None,
        help="Primary From address to test. Default: same as --username.",
    )
    parser.add_argument(
        "--server-email",
        default=None,
        help="Optional SERVER_EMAIL-style From address to test as a second message.",
    )
    parser.add_argument(
        "--custom-from",
        action="append",
        default=[],
        help="Additional custom From address to test. Can be supplied more than once.",
    )
    parser.add_argument(
        "--password-env",
        default="SMTP_PASSWORD",
        help="Environment variable containing the SMTP password. Default: SMTP_PASSWORD.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Socket timeout in seconds. Default: 20.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable smtplib protocol debug output. Do not use this in shared terminals.",
    )
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="Only test TCP, STARTTLS, and login. Do not send any messages.",
    )
    return parser.parse_args()


def get_password(username: str, env_name: str) -> str:
    """Read the SMTP password from an environment variable or prompt."""
    password = os.getenv(env_name)
    if password:
        return password
    return getpass.getpass(f"SMTP password for {username}: ")


def build_message(from_email: str, to_email: str, label: str) -> EmailMessage:
    """Build a small diagnostic message."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    message = EmailMessage()
    message["From"] = from_email
    message["To"] = to_email
    message["Subject"] = f"NBCOT SMTP test - {label}"
    message.set_content(
        "\n".join(
            [
                "NBCOT SMTP test message.",
                "",
                f"Test label: {label}",
                f"From: {from_email}",
                f"To: {to_email}",
                f"UTC time: {now}",
                "",
                "If this arrived, Microsoft 365 accepted the SMTP submission for this From address.",
            ]
        )
    )
    return message


def unique_sender_tests(args: argparse.Namespace) -> list[tuple[str, str]]:
    """Return unique From-address tests while preserving user-provided order."""
    tests = [("authenticated sender", args.from_email or args.username)]
    if args.server_email:
        tests.append(("SERVER_EMAIL", args.server_email))
    tests.extend((f"custom From #{index}", value) for index, value in enumerate(args.custom_from, start=1))

    seen = set()
    unique = []
    for label, address in tests:
        normalized = address.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append((label, address))
    return unique


def main() -> int:
    """Run the SMTP test."""
    args = parse_args()
    password = get_password(args.username, args.password_env)
    if not password:
        print("ERROR: empty SMTP password", file=sys.stderr)
        return 2

    print(f"Connecting to {args.host}:{args.port} with timeout {args.timeout}s...")
    try:
        with smtplib.SMTP(args.host, args.port, timeout=args.timeout) as smtp:
            if args.debug:
                smtp.set_debuglevel(1)

            smtp.ehlo()
            print("TCP connect/EHLO: OK")

            context = ssl.create_default_context()
            smtp.starttls(context=context)
            smtp.ehlo()
            print("STARTTLS: OK")

            smtp.login(args.username, password)
            print(f"SMTP AUTH login as {args.username}: OK")

            if args.no_send:
                print("--no-send selected; not sending test messages.")
                return 0

            for label, from_email in unique_sender_tests(args):
                print(f"Sending {label} test from {from_email} to {args.to}...")
                message = build_message(from_email, args.to, label)
                refused = smtp.send_message(message, from_addr=from_email, to_addrs=[args.to])
                if refused:
                    print(f"FAILED: recipient refused for {label}: {refused}", file=sys.stderr)
                    return 1
                print(f"Send {label}: OK")

    except (socket.timeout, TimeoutError) as exc:
        print(f"ERROR: connection timed out. This usually means port {args.port} is blocked: {exc}", file=sys.stderr)
        return 1
    except ConnectionRefusedError as exc:
        print(f"ERROR: connection refused by {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1
    except ssl.SSLError as exc:
        print(f"ERROR: TLS/STARTTLS failed: {exc}", file=sys.stderr)
        return 1
    except smtplib.SMTPAuthenticationError as exc:
        print(f"ERROR: SMTP authentication failed: {exc.smtp_code} {exc.smtp_error!r}", file=sys.stderr)
        print("Check the password and whether Authenticated SMTP is enabled for the mailbox.", file=sys.stderr)
        return 1
    except smtplib.SMTPSenderRefused as exc:
        print(f"ERROR: sender refused for {exc.sender}: {exc.smtp_code} {exc.smtp_error!r}", file=sys.stderr)
        print("For Microsoft 365, custom From addresses require Send As permission or an accepted alias.", file=sys.stderr)
        return 1
    except smtplib.SMTPRecipientsRefused as exc:
        print(f"ERROR: recipient refused: {exc.recipients}", file=sys.stderr)
        return 1
    except smtplib.SMTPResponseException as exc:
        print(f"ERROR: SMTP command failed: {exc.smtp_code} {exc.smtp_error!r}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: network/socket error: {exc}", file=sys.stderr)
        return 1

    print("All requested SMTP tests succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
