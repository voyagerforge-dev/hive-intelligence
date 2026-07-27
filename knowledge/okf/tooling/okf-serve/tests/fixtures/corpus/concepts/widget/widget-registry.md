---
type: dbobject
kind: table
title: WIDGET_REGISTRY
description: Registry of assembled widgets, one row per serial number.
product: widget
module: CORE
platform:
- postgres
tags:
- table
- CORE
resource: ''
---

| Column | Type | Notes |
|---|---|---|
| SERIAL_NO | varchar(32) | primary key |
| ASSEMBLED_AT | timestamp | |
| TOLERANCE | numeric(4,2) | |
