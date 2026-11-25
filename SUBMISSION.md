# LeapSpan

**Category** · Intelligent Contracts

LeapSpan provides reversible UTC–TAI conversion and exact elapsed seconds for contracts that use UTC-labeled measurements. It gives an inserted `23:59:60Z` label its own TAI second.

The leader and each validator independently fetch the complete IANA and U.S. Naval Observatory time tables. Each verifies that both formats yield the same UTC transition dates and offsets. Validators require exact agreement on the reconciled transitions and the IANA coverage expiry. A permissionless sync can extend that coverage while preserving the previously agreed history.

The live StudioNet example maps three consecutive UTC labels to TAI seconds 1483228835, 1483228836, and 1483228837. The elapsed time from `2016-12-31T23:59:59Z` to `2017-01-01T00:00:00Z` is two seconds. Both live reconciliations returned the same table digest. GenVM lint and six direct tests passed, covering all 27 historical positive leaps in the captured schedule, a synthetic negative leap, source disagreement, and history rewrites.

- **Repository** · [Source, tests, and documentation](https://github.com/ehsanisildur-ux/leap-span)
- **GenVM checks** · [Lint and direct test run](https://github.com/ehsanisildur-ux/leap-span/actions/runs/45693275752)
- **StudioNet Explorer** · [Deployed contract](https://explorer-studio.genlayer.com/address/0x2535DD895A981F1cfb8d2F4bDf626205B477A8Bb)
- **Proofs** · [Finalized receipts and round-trip results](https://github.com/ehsanisildur-ux/leap-span/blob/main/proofs/studionet.json)
