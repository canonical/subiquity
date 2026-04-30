# Security policy

## Supported versions

There are two main types of Subiquity releases.

* Subiquity releases corresponding to an Ubuntu release, which are included in
  corresponding installer ISOs, e.g.:
    * 24.04, 24.04.1, 24.04.2, 25.10, 26.04, ...
* Patch releases that are only offered as installer refreshes, e.g.:
    * 24.10.1, 24.04.4.1, ...

We typically support all Subiquity versions that correspond to an Ubuntu
release, until that Ubuntu release becomes EOL.

For Ubuntu LTSes, we typically stop delivering bug fixes after the .5 ISO is
out. However, we can still issue patch releases for high or critical security
issues when relevant.

A patch release of Subiquity is only supported until another release supersedes
it, or until the corresponding Ubuntu release becomes EOL.

## What qualifies as a security issue

The goal of Subiquity is to deploy a new Ubuntu system.

In general, any vulnerability that allows a third-party, without authorized
access to the machine, to gain partial or full control over what gets deployed
will be considered a security issue.

Subiquity runs in a live installer environment, where we consider that any user
process has a trivial path to full root privileges (i.e., `sudo` is typically
configured to allow root access without a password). Therefore, any
vulnerability that only allows the live environment user to escalate privileges
further will not be considered a security issue.

## Reporting a vulnerability

If you discover a security vulnerability, follow the steps outlined below to report it:

1. Do not publicly disclose the vulnerability before discussing it with us.
2. Report a bug at https://bugs.launchpad.net/subiquity

    **Important**: Remember to set the information type to *Private Security*. This is set with the field below the Bug Description. Click the edit icon under "This bug contains information that is:", and choose *Private Security*.
3. Provide detailed information about the vulnerability, including:
   - A description of the vulnerability
   - Steps to reproduce the issue
   - Potential impact and affected versions
   - Suggested mitigation, if possible

The [Ubuntu Security disclosure and embargo policy](https://ubuntu.com/security/disclosure-policy) contains more information about what you can expect when you contact us and what we expect from you.

The Subiquity team will be notified of the vulnerability and will work with you
to determine whether it qualifies as a security issue. From there, we will
handle developing a fix, securing a CVE assignment if necessary, and
coordinating the release.
