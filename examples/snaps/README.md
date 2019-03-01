## Sample snap data

This directory contains canned responses from snapd's REST API that
are used by default in dry-run mode. (You can pass
--no-snaps-from-examples flag to talk to your local snapd instead). It
was generated something like this:

```
$ curl --silent --unix-socket /var/run/snapd.socket a/v2/find?section=server | jq . > v2-find-section=server.json
$ for x in $(cat v2-find-section=server.json | jq -r '.result  | .[].name'); do curl --silent --unix-socket /var/run/snapd.socket a/v2/find?name=$x | jq . > v2-find-name=$x.json; done
```
