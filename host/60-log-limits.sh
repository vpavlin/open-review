#!/usr/bin/env bash
# Keep logs from filling the disk (run as root on the review host).
#
# 2026-11-02: /var/log/syslog reached 175 GB in a day and filled the 193 GB
# disk. The WhisperBox bot (wb-bot.service, a logosctl daemon) logs its
# delivery module at debug level, and the DHT's liveness probes alone were
# about ten thousand lines a second, all copied from the journal into syslog.
# The journal keeps them under its own size cap; syslog does not need them.
set -euo pipefail

cat > /etc/rsyslog.d/10-drop-delivery-debug.conf <<'CONF'
# The delivery module's debug lines (logosctl, the WhisperBox bot) stay in the
# journal, which caps itself; copied here they filled the disk (2026-11-02).
if $programname == 'logosctl' and $msg contains '] DBG ' then stop
CONF

cat > /etc/logrotate.d/zz-syslog-maxsize <<'CONF'
# Rotate syslog whenever it passes 1 GB, not only daily (2026-11-02: 175 GB).
/var/log/syslog
{
	maxsize 1G
	rotate 4
	missingok
	notifempty
	compress
	delaycompress
	sharedscripts
	postrotate
		/usr/lib/rsyslog/rsyslog-rotate
	endscript
}
CONF
# The stock rule names syslog too; logrotate refuses a file named twice.
sed -i '\#^/var/log/syslog$#d' /etc/logrotate.d/rsyslog

# logrotate runs daily by default; hourly, so maxsize is checked in time.
mkdir -p /etc/systemd/system/logrotate.timer.d
cat > /etc/systemd/system/logrotate.timer.d/hourly.conf <<'CONF'
[Timer]
OnCalendar=
OnCalendar=hourly
CONF
systemctl daemon-reload
systemctl restart rsyslog logrotate.timer
logrotate -d /etc/logrotate.conf 2>&1 | grep -iE 'error' || echo "logrotate config ok"
