# Security policy

Hive is an engine you run yourself. It holds no service we operate on your behalf, so a
vulnerability here is a vulnerability in software on your machine or in your deployment. We
would still very much like to hear about it.

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Email **security@voyagerforge.dev**. That route always works and is the one to use if you are
unsure.

Once private vulnerability reporting is enabled on this repository, the preferred route is
GitHub's own: the **Security** tab, then **Report a vulnerability**. It opens a private thread
visible only to you and the maintainers, and it keeps the discussion attached to the code. If that
tab offers you no such button, the feature is not on yet - use the email address above.

A report is most useful when it says which package it concerns (`vf-hive-prep`, `vf-hive-gen`,
`vf-hive-serve`, `vf-hive-dbparse`, `vf-hive-zendesk`, or `hive-author`, which is not published to
PyPI and is reported against its source in `tooling/hive-author`), which version, what an attacker
can do with it, and the shortest sequence of steps that shows it. A proof of concept is welcome; a
working exploit is not required.

Please do not include real customer data, credentials, or a corpus in a report. If reproducing
the issue needs one, describe its shape instead and we will work out a synthetic case.

## What to expect

A person reads these, not a rota. We aim to acknowledge a report within a few business days and
to tell you plainly what we think of it, including when we think it is not a vulnerability. There
is no paid bounty and no guaranteed response time.

If we agree it is a vulnerability, the fix ships as a new release of the affected distributions,
and the release notes say what was fixed. We will credit you unless you would rather we did not.
We ask that you hold the details until that release is out.

## Which versions get fixes

The released distributions ship as **one engine at one version**, so a security release moves
all of them together. Fixes go into the current minor series on PyPI (at the time of writing,
`0.6.x`) as a new patch release. Older minors receive nothing; upgrading to the current minor is
the supported path. See
[docs/architecture/engine-distribution.md](docs/architecture/engine-distribution.md) for how a
version is stamped and what a consumer pins.

## Scope

In scope: the code in this repository and the wheels published from it.

Out of scope: any corpus (no corpus is distributed here, and one belongs to whoever produced it),
any particular deployment of Hive, and the third-party services a deployment may talk to. A
finding in a dependency belongs upstream first; tell us as well if it reaches a user through how
we call it.
