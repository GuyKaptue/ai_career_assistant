# Privacy overview

The application is designed around the principle that personal career data should remain under the control of the user and the instance owner. The project supports self-hosting and keeps the database and authorization flow aligned with the idea that user information should not be treated as a commodity.

The exporter and document-generation layers are designed to work with user-supplied content and to store it in a controlled, user-scoped model. The architecture does not assume that data should be pushed to a third-party service without a clear configuration decision.

This also fits the open-source goal of the project: the stack should be familiar enough for a community maintainer to run it responsibly and adapt it to their own hosting or compliance requirements.

## Practical boundaries

- user identity must come from the authenticated subject, not a fake local placeholder
- stored documents and applications remain scoped by `user_id` and are validated in the API layer
- external job or model settings must be configured explicitly; no silent fallback to placeholder data is accepted
- deployment configuration should make it clear which environment owns the data and which keys are required for secure operation
