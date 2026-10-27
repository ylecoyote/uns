# MIP Integration Sample

This directory contains the proving integration between UNS and Market
Insights Platform (MIP). It is **sample material**, not part of the UNS
public API. The adapter demonstrates how a host application binds UNS
into its execution flow and emits governance signals for trading-domain
events.

To use it in your own deployment, copy or symlink `adapter.py` into your
host project and adapt the signal types to your domain. UNS does not
ship this adapter as a public class.

The adapter imports from `notification.integrations.app_boundary`, so your
host environment must have `uns` (or the `uns[adapters]` extra)
installed for those imports to resolve.

See `docs/SECURITY-MODEL.md` for the UNS product boundary.
