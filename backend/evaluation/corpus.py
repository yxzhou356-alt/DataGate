"""Hand-labelled synthetic examples; markers are annotation syntax, not detectors.

Development and heldout examples use separate phrasings. This small convenience
benchmark is neither representative production data nor evidence of anonymity.
"""

import re

_ANNOTATION = re.compile(r"\[\[(PERSON|EMAIL|PHONE)\|(.+?)\]\]")

# Authored labels are explicit, independent of either detector's predictions.
DEVELOPMENT = [
    "My name is [[PERSON|Alice Morgan]] and the reset link failed.",
    "Please ask [[PERSON|Daniel Brooks]] to review the export.",
    "The account owner is [[PERSON|Priya Shah]].",
    "[[PERSON|Marcus Chen]] reported a missing invoice.",
    "Reach me at [[EMAIL|alice.demo@example.com]].",
    "Call [[PHONE|213-555-0105]] after lunch.",
    "[[PERSON|Elena Garcia]] uses [[EMAIL|elena.demo@example.org]].",
    "[[PERSON|James Miller]] called [[PHONE|(310) 555-0109]].",
    "The March release has a broken chart.",
    "Our Apple integration stopped working.",
    "Exporting to CSV takes too long.",
    "The Seattle support office is closed.",
    "My colleague [[PERSON|Sam Rivera]] found the bug.",
    "[[PERSON|Nora Patel]] and [[PERSON|Liam Ford]] need a reply.",
    "Please email [[EMAIL|support.demo+case@example.net]] for details.",
    "The total is 1200 and the ticket number is 404.",
]

HELDOUT = [
    "A customer named [[PERSON|Sofia Bennett]] cannot see the dashboard.",
    "The new administrator, [[PERSON|Owen Clarke]], requested a refund.",
    "I am [[PERSON|Mei Lin]]; my password reset did not arrive.",
    "The escalation belongs to [[PERSON|Fatima Hassan]].",
    "Yesterday [[PERSON|Noah Williams]] reproduced the problem.",
    "The report was signed by [[PERSON|Gabriela Santos]].",
    "Could [[PERSON|Amina Yusuf]] receive the corrected invoice?",
    "On the call, [[PERSON|Victor Petrov]] described slow uploads.",
    "The customer representative is [[PERSON|Haruto Tanaka]].",
    "For the follow-up, contact [[PERSON|Zoe Martin]].",
    "[[PERSON|Leila Ahmed]] said [[PERSON|Oscar Reed]] has the screenshots.",
    "My colleague [[PERSON|Jordan]] handles renewals.",
    "A customer called [[PERSON|May]] needs help with billing.",
    "We spoke with [[PERSON|Hope]] about her account.",
    "the requester is [[PERSON|maya singh]], not the account owner.",
    "👋 Please reply to [[PERSON|Chloe Davis]] about the café export.",
    "[[PERSON|Ana Maria Lopez]] asked for a transcript.",
    "This message is from Dr. [[PERSON|Ethan Stone]].",
    "My surname is [[PERSON|Nguyen]] and I cannot log in.",
    "[[PERSON|Alex Johnson]] wrote: ‘My CSV has extra quotes.’",
    "Send the updated receipt to [[EMAIL|receipt.demo@example.com]].",
    "The backup address ([[EMAIL|backup.demo@example.co.uk]]) still works.",
    "My current number is [[PHONE|+1 415-555-0118]].",
    "Please retry [[PHONE|212.555.0124]] instead.",
    "[[PERSON|Clara Evans]] can be reached at [[EMAIL|clara.demo@example.net]].",
    "The caller [[PERSON|Isaac Brown]] left [[PHONE|617-555-0137]].",
    "Forward this to [[PERSON|Mina Kim]] at [[EMAIL|mina.demo+help@example.org]].",
    "I am [[PERSON|Sara Ali]]; call [[PHONE|(323) 555-0142]].",
    "The Jordan office needs a better network connection.",
    "May we move the renewal date to June?",
    "We hope the next release fixes the problem.",
    "Apple and Microsoft exports have the same layout issue.",
    "Paris is the selected billing region.",
    "A silver label appears next to the failed payment.",
    "The customer name field is blank in the report.",
    "Order 123456 has quantity 42 and amount 200.50.",
    "The message says hello, but contains no contact details.",
    "Our Friday deployment changed the login screen.",
    "The product called Nova fails after ten minutes.",
    "The report header contains Name, Email, and Phone.",
]


def _example(marked: str, example_id: str, split: str) -> dict:
    chunks, entities, cursor, length = [], [], 0, 0
    for match in _ANNOTATION.finditer(marked):
        prefix = marked[cursor:match.start()]
        chunks.append(prefix)
        length += len(prefix)
        category, value = match.groups()
        entities.append({"start": length, "end": length + len(value), "entity_type": category})
        chunks.append(value)
        length += len(value)
        cursor = match.end()
    chunks.append(marked[cursor:])
    return {"id": example_id, "split": split, "text": "".join(chunks), "entities": entities}


def examples(split: str) -> list[dict]:
    if split not in {"development", "heldout"}:
        raise ValueError("Choose development or heldout.")
    source = DEVELOPMENT if split == "development" else HELDOUT
    return [_example(marked, f"{split}-{index + 1:03d}", split) for index, marked in enumerate(source)]
