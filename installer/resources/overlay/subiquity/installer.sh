#!/bin/bash
LASTCON=$(cat /proc/cmdline | fmt -w 1 | grep ^console= | tail -n 1)
case $LASTCON in
    console=ttyS[0-9])
        SERIAL="-o --serial"
        systemctl stop serial-getty@ttyS0.service
        ;;
    console=tty[0-9])
        SERIAL=""
        chvt 1
        systemctl stop getty@tty1.service;
        ;;
esac
# generate service file
cat <<EOF >/lib/systemd/system/subiquity.service
[Unit]
Description=Ubuntu Servier Installer Service
After=getty@tty1.service

[Service]
Environment=PYTHONPATH=/usr/local
ExecStart=-/sbin/agetty -n --noclear -l /usr/local/bin/subiquity-tui ${SERIAL} console vt100
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=yes
KillMode=process
Type=idle
Restart=always
StandardInput=tty-force
StandardOutput=tty
StandardError=tty
TTYPath=/dev/console

[Install]
WantedBy=default.target
EOF

systemctl enable subiquity.service
systemctl start subiquity
