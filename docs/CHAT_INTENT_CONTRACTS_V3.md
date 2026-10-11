# NEYAN intent contracts — V3

These contracts define the classifier's semantic boundary only. They do not
authorize database changes; the server state machine and ownership checks do.

| Intent | Contract | Must not mean |
|---|---|---|
| `book_trip` | Explicit request to reserve/create/hold a seat or trip. | Browsing, price, capacity, or schedule questions. |
| `availability_inquiry` | Ask whether seats/capacity remain; no reservation requested. | A request to hold or book a seat. |
| `trip_search` | Discover possible routes/departures/options. | Requesting details for a known trip or a reservation. |
| `trip_information` | Ask when, where, duration, stops, or route details of a trip. | Searching for options or asking price/capacity. |
| `price_inquiry` | Ask fare/cost/price only. | Reserving a ticket. |
| `cancel_booking` | Cancel an already persisted booking, subject to ownership/workflow validation. | Declining an uncommitted conversational proposal. |
| `confirmation` | Explicit affirmative while a server state is awaiting confirmation. | General “yes” outside an awaiting-confirmation state. |
| `cancellation` | Explicit decline/abort of the current uncommitted conversational action. | Cancelling a stored booking. |
| `maintenance_request` | Request maintenance or report a vehicle fault requiring a maintenance flow. | General service dissatisfaction. |
| `complaint` | Express dissatisfaction or request a complaint process. | A repair request or generic help. |
| `company_information` | Ask about transportation companies/operators. | Whether a particular departure has seats. |
| `help` | Ask how to use the service or what the assistant can do. | A concrete business action. |
| `greeting` | Social opening without a substantive request. | A mixed message containing a business action. |
| `goodbye` | Social closing without a substantive request. | Cancelling a pending action. |
| `general_conversation` | Non-operational small talk outside the transport workflow. | Any actionable transport/maintenance request. |

## Context rule

For `STATE_BOOKING_CONFIRM`, `STATE_MAINT_CONFIRM`, and Forming Trip
confirmation states, `intents.is_confirmation()` and
`intents.is_cancellation()` are the authoritative deterministic interpreters
for short replies such as “نعم”, “أكيد”, “توكلنا”, “ثبت”, “تابع”, “yes”,
“لا”, “تراجع”, “مش هسا”, and “abort”. The model cannot bypass them.

The existing state machine already applies this rule in its finalizers and
Forming Trip handlers. `cancel_booking` remains separate and must pass the
existing persisted-booking and ownership validation.
