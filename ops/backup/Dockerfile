FROM postgres:17-alpine

RUN apk add --no-cache restic
COPY backup.sh /usr/local/bin/partner-reports-backup
COPY restore-test.sh /usr/local/bin/partner-reports-restore-test
RUN addgroup -g 10001 backup \
    && adduser -D -H -u 10001 -G backup backup \
    && chmod 0555 /usr/local/bin/partner-reports-backup \
        /usr/local/bin/partner-reports-restore-test

USER backup
ENTRYPOINT ["/usr/local/bin/partner-reports-backup"]
