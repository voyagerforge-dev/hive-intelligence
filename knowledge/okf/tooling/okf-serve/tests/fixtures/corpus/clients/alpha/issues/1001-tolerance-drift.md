---
type: issue
title: Tolerance drift after sealing
description: Widgets left the sealing stage outside tolerance because calibration
  ran before the seal had fully cured.
client: alpha
product: widget
platform: bench
module: calibration
related:
- widget/calibration-routine
- widget/assembly-process
tags:
- calibration
- drift
resource: ''
timestamp: '2026-02-03'
status: closed
---

Calibration was running immediately after sealing. Adding a cure delay resolved it.
