#!/bin/sh

# Let appmgrd resolve the installed document's registered reader handler.
exec /usr/bin/lipc-set-prop com.lab126.appmgrd start \
    file:///mnt/us/documents/RupertsMission.mobi
