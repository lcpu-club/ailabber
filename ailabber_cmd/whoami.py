"""whoami command - Show current user"""
import os

current_username = os.environ.get('USER', 'unknown')


def cmd_whoami(args):
    """Show current user"""
    print(f"Current user: {current_username}")
    return current_username
