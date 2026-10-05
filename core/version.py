"""How new this server's API is, as one number.

The frontend build is uploaded by hand; the backend deploys itself whenever
main changes. So the two can be out of step, and for two days they were: new
screens called addresses the server did not have yet, and nothing said so.

Raise API_LEVEL by one, and REQUIRED_API_LEVEL in
PaPerProjectFront/src/config/apiLevel.js to the same number, in any change
where the screens start needing something new from the server (a new address,
a field they rely on, an answer that changed shape). The screens ask
GET /api/version and show "being updated" while the server is behind
(components/common/ServerVersionNotice.jsx). core/tests_version.py keeps the
two numbers equal in the repository.
"""

API_LEVEL = 1
