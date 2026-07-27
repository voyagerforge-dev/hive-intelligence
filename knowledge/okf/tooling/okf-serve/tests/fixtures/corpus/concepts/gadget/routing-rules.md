---
type: concept
title: Gadget Routing Rules
description: How a gadget is routed between stations, and the fallback applied
  when a station is unavailable.
product: gadget
platform: line
tags:
- routing
resource: ''
sources:
- kind: fixture-doc
  ref: gadget-routing.md
---

Gadgets route to the nearest free station. If none is free within two cycles the
gadget is held at the inbound buffer.
