.. py:currentmodule:: lsst.ts.mtreflector

.. _lsst.ts.version_history:

###############
Version History
###############

.. towncrier release notes start

v0.1.3 (2025-06-23)
===================

Bug Fixes
---------

- Published ReflectorStatus when connected, disconnected and unknown. (`DM-51109 <https://rubinobs.atlassian.net//browse/DM-51109>`_)
- Changed commanded channels to be CIO0 and CIO1 for open/close of reflector actuator. (`DM-51344 <https://rubinobs.atlassian.net//browse/DM-51344>`_)


v0.1.2 (2025-05-18)
===================

Bug Fixes
---------

- Fixed conda recipe to build correctly. (`DM-48352 <https://rubinobs.atlassian.net//browse/DM-48352>`_)


Other Changes and Additions
---------------------------

- Removed mtreflector prefix from module names. (`DM-48352 <https://rubinobs.atlassian.net//browse/DM-48352>`_)
- Simplified handle_summary_state in csc.py. (`DM-48352 <https://rubinobs.atlassian.net//browse/DM-48352>`_)


v0.1.0
------

* The first release.
