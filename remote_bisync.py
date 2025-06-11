#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
#
# Remote File Sync Tool base on Rclone
#
# Copyright (C) 2025 Yeh, Hsin-Hsien <yhh76227@gmail.com>
#
import argparse
import datetime
import json
import os
import random
import subprocess
import smtplib
import sys
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jsonschema import validate, ValidationError
from pathlib import Path


def get_schema():
    """Get JSON schema."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "client": { "type": "string" },
            "remote": { "type": "string" },
            "retry_connect_times": { "type": "integer" },
            "retry_connect_interval": { "type": "integer" },
            "retry_lock_times": { "type": "integer" },
            "retry_lock_interval": { "type": "integer" },
            "retry_lock_randtime": { "type": "integer" },
            "log_directory": { "type": "string" },
            "email_send": { "type": "boolean" },
            "receiver_mail": { "type": "string", "format": "email" },
            "smtp_user": { "type": "string", "format": "email" },
            "smtp_pass": { "type": "string" },
            "smtp_server": { "type": "string" },
            "smtp_port": { "type": "integer" },
            "sync_directory": {
                "type": "object",
                "patternProperties": {
                    ".*": {
                        "type": "object",
                        "properties": {
                            "remote": { "type": "string" },
                            "client": { "type": "string" },
                            "exclude": {
                                "type": "array",
                                "items": { "type": "string" }
                            }
                        },
                        "required": [ 
                            "remote", "client", "exclude"
                        ],
                        "additionalProperties": False
                    }
                }
            }
        },
        "required": [
            "client", "remote", "retry_connect_times", "retry_connect_interval", 
            "retry_lock_times", "retry_lock_interval", "retry_lock_randtime", 
            "log_directory", "email_send", "sync_directory"
        ],
        "if": {
            "properties": {
                "email_send": { "const": True }
            }
        },
        "then": {
            "required": [
                "receiver_mail", "smtp_user", "smtp_pass", "smtp_server", 
                "smtp_port"
            ]
        },
        "additionalProperties": False
    }

    return schema


def remote_bisync(args, config: dict):
    """Remote bisync process."""
    timestamp = lambda: datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    if args.rclone_log is not None:
        logfile = Path(args.rclone_log)
    else:
        filename = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
        logfile = Path(config["log_directory"]) / filename

    if args.print_to_log:
        pout = open(logfile, "w")
    else:
        pout = sys.stdout

    if args.sync:
        sync_flow = "SYNC-FLOW"
    else:
        sync_flow = "BISYNC-FLOW"

    # Remote connect check
    client_srv = config["client"]
    remote_srv = config["remote"]
    retry_limit = config["retry_connect_times"]
    retry_inter = config["retry_connect_interval"]
    connect_pass = False
    retry_times = 0

    print("{} {}: Connect to the remote server \"{}\"".format(timestamp(), 
          sync_flow, remote_srv), file=pout)

    while not connect_pass:

        result = subprocess.run(["rclone", "lsd", f"{remote_srv}:", 
                                 "--timeout=10s", 
                                 "--contimeout=5s", 
                                 "--low-level-retries=1",
                                 "--fast-list"], capture_output=True, text=True)

        if result.returncode == 0:
            print("{} {}: \"{}\" connect pass".format(timestamp(), sync_flow, 
                  remote_srv), file=pout)
            connect_pass = True
        elif retry_times == retry_limit:
            print(f"{timestamp()} {sync_flow}: " + 
                  f"The number of connection retry attempts has reached " + 
                  f"the configured limit, terminate. ({remote_srv})", file=pout)
            exit(1)
        else:
            print(f"{timestamp()} {sync_flow}: " + 
                  f"\"{remote_srv}\" connect fail, retry. " + 
                  f"({retry_times}/{retry_limit})", file=pout)
            time.sleep(retry_inter)
            retry_times += 1

    if args.targets is not None:
        sync_targets = {}
        for target in args.targets:
            if target in config["sync_directory"]:
                sync_targets[target] = config["sync_directory"][target]
    else:
        sync_targets = config["sync_directory"]

    for target, target_info in sync_targets.items():
        remote_path = f"{remote_srv}:" + target_info["remote"]
        client_path = target_info["client"]
        exclude_list = target_info["exclude"]

        # Remote lock check
        lock_path = f"{remote_path}/{client_srv}.rclock"
        lock_pass = lock_fail = False
        retry_limit = config["retry_lock_times"]
        retry_inter = config["retry_lock_interval"]
        retry_rand = config["retry_lock_randtime"]
        retry_times = 0

        print("{} {}: Lock remote directory \"{}\"".format(timestamp(), 
              sync_flow, remote_path), file=pout)

        while not (lock_pass or lock_fail):

            cmd = ["rclone", "ls", remote_path, "--max-depth", "1",
                   "--filter", f"- {client_srv}.rclock",
                   "--filter", f"+ *.rclock",
                   "--filter", f"- *"]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.stdout == "":
                subprocess.run(["rclone", "touch", lock_path])
                print("{} {}: \"{}\" lock pass".format(timestamp(), sync_flow, 
                      remote_path), file=pout)
                lock_pass = True
            elif retry_times == retry_limit:
                print(f"{timestamp()} {sync_flow}: " + 
                      f"The number of lock retry attempts has reached " + 
                      f"the configured limit, ignore. ({remote_path})", 
                      file=pout)
                lock_fail = True
            else:
                print(f"{timestamp()} {sync_flow}: " + 
                      f"\"{remote_path}\" lock fail, retry. " + 
                      f"({retry_times}/{retry_limit})", file=pout)
                time.sleep(retry_inter + random.randint(0, retry_rand))
                retry_times += 1

        if lock_fail:
            continue

        # Sync remote data
        sync_mode = ""

        if args.sync:
            cmd = ["rclone", "sync"]
        else:
            cmd = ["rclone", "bisync"]

        if args.resync:
            cmd.append("--resync")
            sync_mode += ", resync"

        if args.reverse:
            if args.sync:
                cmd.extend([client_path, remote_path])
                sync_mode += ", reverse"
            else:
                cmd.extend([remote_path, client_path])
                print("{} {}: Ignore option \"-reverse\"".format(
                      timestamp(), sync_flow), file=pout)
        else:
            cmd.extend([remote_path, client_path])

        if args.dryrun:
            cmd.append("--dry-run")

        if not args.sync:
            cmd.extend([
                "--conflict-resolve", "newer",
                "--conflict-suffix", f"conflict_{remote_srv},conflict_{client_srv}",
                "--force"
            ])

        cmd.extend([
            "-vv", f"--log-file={logfile}", "--checksum",
            "--create-empty-src-dirs",
            "--exclude", f"{client_srv}.rclock",
        ])
        
        for exclude_path in exclude_list:
            cmd.extend(["--exclude", exclude_path])

        if sync_mode != "":
            sync_mode = f"({sync_mode[2:]})"

        print("{} {}: Start sync \"{}\" {}".format(timestamp(), sync_flow, 
              remote_path, sync_mode), file=pout)

        if args.print_to_log:
            pout.close()

        result = subprocess.run(cmd, capture_output=True, text=True)

        if args.print_to_log:
            pout = open(logfile, 'a')

        # Send conflict email
        conflict_found = False
        if config["email_send"]:
            with open(logfile, "r", encoding="utf-8") as log_fp:
                for line in log_fp:
                    if "potential conflicts" in line.lower():
                        conflict_found = True
                        break

        if conflict_found:
            print("{} {}: Conflict detected when sync \"{}\" ".format(
                    timestamp(), sync_flow, remote_path), file=pout)

            msg = MIMEMultipart()
            msg["From"] = (smtp_user := config["smtp_user"])
            msg["To"] = (receiver_mail := config["receiver_mail"])
            msg["Subject"] = f"[{client_srv}] Rclone Sync Conflict"

            msg_body = "Sync conflict occurred.\n" + \
                       "Please log in to the system and check the log file " + \
                       "for manual resolution.\n\n" + \
                       "Sync Mode   : {}\n".format(sync_flow) + \
                       "Remote Path : {}\n".format(remote_path) + \
                       "Client Path : {}\n".format(client_path) + \
                       "Log File    : {}\n".format(logfile.absolute())
            msg.attach(MIMEText(msg_body, "plain"))

            try:
                smtp_srv = config["smtp_server"]
                smtp_port = config["smtp_port"]
                smtp_pass = config["smtp_pass"]
                with smtplib.SMTP_SSL(smtp_srv, smtp_port) as server:
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(smtp_user, receiver_mail, msg.as_string())
                print(f"{timestamp()} {sync_flow}: " + 
                      f"Conflict email sent successfully.", file=pout)
            except Exception as e:
                print(f"Error: {e}")

        # Remove lock
        subprocess.run(["rclone", "delete", lock_path])
        print("{} {}: \"{}\" lock is removed".format(timestamp(), sync_flow, 
              remote_path), file=pout)

    if args.print_to_log:
        pout.close()


def create_argparse() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description='Remote File Sync Tool base on Rclone.')

    parser.add_argument("json_file", help="Sync setting by JSON.") 
    parser.add_argument("-print_to_log", dest="print_to_log", action="store_true", 
                        help="Print the flow log to the rclone log file.")

    sync_gparser = parser.add_mutually_exclusive_group(required=False)
    sync_gparser.add_argument("-sync", dest="sync", action="store_true", 
                              help="Sync mode.")
    sync_gparser.add_argument("-resync", dest="resync", action="store_true", 
                              help="Resync mode.")

    parser.add_argument("-reverse", dest="reverse", action="store_true", 
                        help="Reverse the remote and client.")
    parser.add_argument("-dryrun", dest="dryrun", action="store_true", 
                        help="Do a trial run with no permanent changes.")
    parser.add_argument('-target', dest='targets', metavar='string', nargs='*', 
                        help="Specific sync targets.") 
    parser.add_argument('-rclone_log', dest='rclone_log', metavar='filepath', 
                            help="Specific the rclone log path manually.") 

    return parser


def main():
    """Main funcrtion."""
    parser = create_argparse()
    args = parser.parse_args()

    with open(args.json_file, "r", encoding="utf-8") as json_fp:
        config = json.load(json_fp)

    try:
        validate(instance=config, schema=get_schema())
    except ValidationError as e:
        print("\n[ERROR] JSON Schema check fail.\n")
        print(e)
        exit(1)

    remote_bisync(args, config)


if __name__ == "__main__":
    main()


