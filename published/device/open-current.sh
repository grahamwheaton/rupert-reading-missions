#!/bin/sh

# K4/KDK reader URI. The fixed filename avoids URL-escaping ambiguity.
exec /usr/bin/lipc-set-prop com.lab126.appmgrd start \
    app://com.lab126.booklet.reader/mnt/us/documents/RupertsMission.mobi
