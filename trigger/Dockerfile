# Tiny image whose only job is to POST two workflow_dispatch calls.
# The script is plain text on disk deliberately -- an inline/encoded command
# would be unreadable in the Machine config and unreviewable in git.
FROM alpine:3.20
RUN apk add --no-cache curl
COPY trigger.sh /usr/local/bin/trigger.sh
RUN chmod +x /usr/local/bin/trigger.sh
ENTRYPOINT ["/bin/sh", "/usr/local/bin/trigger.sh"]
