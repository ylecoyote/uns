# MIP Integration Sample

This directory contains the proving integration between AGSignal and Market
Insights Platform (MIP). It is **sample material**, not part of the AGSignal
public API. The adapter demonstrates how a host application binds AGSignal
into its execution flow and emits governance signals for trading-domain
events.

To use it in your own deployment, copy or symlink `adapter.py` into your
host project and adapt the signal types to your domain. AGSignal does not
ship this adapter as a public class.

The adapter imports from `notification.integrations.app_boundary`, so your
host environment must have `agsignal` (or the `agsignal[adapters]` extra)
installed for those imports to resolve.

See `docs/SECURITY-MODEL.md` for the AGSignal product boundary.
