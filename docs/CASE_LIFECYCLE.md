# Case lifecycle

Status and approval state are separate. A case can be approved and still be waiting for fulfilment.

## Allowed moves

| From | To |
| --- | --- |
| new | awaiting information, classified, cancelled |
| awaiting information | classified, cancelled |
| classified | assigned, awaiting information, cancelled |
| assigned | awaiting approval, in progress, awaiting fulfilment, awaiting information, cancelled |
| awaiting approval | approved, rejected, awaiting information, cancelled |
| approved | awaiting fulfilment, in progress, cancelled |
| rejected | closed, awaiting information |
| in progress | awaiting fulfilment, resolved, awaiting information, cancelled |
| awaiting fulfilment | in progress, resolved, cancelled |
| resolved | closed, in progress |
| closed | in progress |
| cancelled | none |

Closed cannot move to approved. Rejected cannot open fulfilment. The API returns `invalid_transition` and writes nothing.

## Intake rules

- Dedup key is the support mailbox plus the provider message id.
- A repeated message updates nothing except a suppression event.
- A reply that quotes `NS-####` is appended only when the sender is that case's requester.
- Auto-replies and the wrong mailbox do not create cases.
- Unknown senders do not create cases and do not create directory rows.

## Acknowledgement

The stored acknowledgement contains the case number, title, received timestamp and the next step. It tells the reader to sign in rather than to reply with secrets. Delivery status stays `not_delivered_channel_unconfigured` until a mailbox connector exists.
