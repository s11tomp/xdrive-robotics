---
name: Bug report
about: Something on the board or in the tools doesn't work as documented
---

**What happened, and what did you expect?**

**Steps to reproduce** (commands, settings changed, what the motor was doing)

**Setup**
- Board (MKS XDRIVE Mini or another ODrive v3.6 clone), and its `hw_version_*`:
- Firmware version (`fw_version_*`, or the commit you built):
- Motor (model, KV, pole pairs) and load:
- Supply voltage, brake resistor:
- Host OS and Python version:

**Board dump:** attach the `logs/*_dump.json` from `python tools/dump_board.py` (it has the config, errors and versions).
