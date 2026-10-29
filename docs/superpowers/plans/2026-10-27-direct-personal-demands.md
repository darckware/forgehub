# Direct personal demand registration

Goal: Marcelo explicitly clarified that requests already present in WhatsApp groups must be registered directly as Personal Demands, without capture suggestions. The demand itself must preserve whether the source is a WhatsApp group or a contact, and which one.

Architecture: reuse the existing Personal Demand form/domain and output origin structure. Add nullable persisted origin and unique source key to the demand itself; legacy suggestion-based origin remains readable. Expose direct demand registration to Maia using real monitored messages or real contact records, with audit and idempotency. No automatic intake from third-party content.

1. Add failing isolated API tests for direct group/contact registration, persisted origin, repeated/concurrent requests and zero new suggestion rows.
2. Add an additive migration, validated source resolution and direct creation on the existing demand route; preserve old suggestion conversion.
3. Expose direct MCP tools and update Maia's scoped guide/configuration to distinguish authorized direct demands from optional suggestions.
4. Run isolated tests and build the compatible backend release, publish after backup, verify tools and reads. Never insert fictitious production records; do not restart the shared gateway without new authorization.

Validation: API output must appear in `/personal/demands`, preserve group/contact identity, reuse the same ID on retries, reject unmonitored/fabricated sources and retain existing contact conversion tests.
