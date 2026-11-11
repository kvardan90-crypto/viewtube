# ViewTube

- Keep authorization centralized in app/services.py. Apply the same rules to API metadata, comments, video bytes and thumbnails.
- Treat uploads as untrusted binary files. Process them in the worker with explicit format and protocol limits.
- Keep the UI same-origin and render user input as text with DOM APIs.
- Run the critical path tests when changing upload, access control or moderation. See README.md for the command.
- Keep secrets, service data and local dependencies out of Git and the submission ZIP.
