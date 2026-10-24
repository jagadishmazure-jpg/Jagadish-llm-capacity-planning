"""Seeded synthetic text for four workloads. All companies and people are fictional.

The generator builds text from small phrase banks so the token counter has something
realistic to measure: short chat questions, long contracts, source code and articles.
"""

from __future__ import annotations

import random

COMPANIES = ["Kestrel Lane Software", "Orchard Row Legal", "Pinecrest Mutual", "Tidewater Clinics", "Juniper Freight"]

_CHAT = [
    "How do I reset my password?",
    "What are your opening hours on Sunday?",
    "Can I change the delivery address for order 48213?",
    "Is there a fee for paying late?",
    "Where can I download last month's invoice?",
    "Do you ship to Canada?",
    "How long does a refund take?",
    "Can you explain the difference between the basic and the pro plan?",
    "My login code never arrived, what should I do?",
    "What does clause 4 mean in simple words?",
]

_CLAUSE = [
    "The Supplier shall deliver the Goods to the Premises within {n} business days of the Order Date.",
    "Either Party may terminate this Agreement upon {n} days written notice to the other Party.",
    "The Customer shall pay each undisputed invoice within {n} days of receipt, failing which interest accrues.",
    "Neither Party shall be liable for any indirect, incidental or consequential loss arising under this Agreement.",
    "All Confidential Information shall remain the property of the disclosing Party for a period of {n} years.",
    "The total liability of the Supplier under this Agreement shall not exceed {n} percent of the annual fees.",
    "Any dispute shall first be referred to senior representatives, who shall meet within {n} days.",
    "The Supplier warrants that the Services will be performed with reasonable skill, care and diligence.",
]

_CODE = [
    "def calculate_total(items: list[dict]) -> float:\n    return sum(i['price'] * i['qty'] for i in items)\n",
    "class OrderRepository:\n    def __init__(self, session):\n        self.session = session\n",
    "    def get(self, order_id: int):\n        return self.session.query(Order).filter_by(id=order_id).one()\n",
    "if response.status_code != 200:\n    raise RuntimeError(f'upstream failed: {response.status_code}')\n",
    "for index, row in enumerate(rows):\n    if not row.get('email'):\n        errors.append(index)\n",
    "async def fetch(url):\n    async with httpx.AsyncClient(timeout=10) as client:\n        return await client.get(url)\n",
]

_ARTICLE = [
    "Regional freight volumes rose for the third quarter in a row, driven by demand for refrigerated transport.",
    "Analysts expect the new warehouse in the northern corridor to cut average delivery times by a full day.",
    "The company said fuel costs remained the largest single expense, ahead of wages and maintenance.",
    "Customer complaints fell after the switch to live tracking, according to the internal quarterly review.",
    "Smaller carriers are pooling loads to compete with national operators on long-distance routes.",
    "The board approved a modest dividend while warning that interest rates could slow expansion plans.",
]


def chat_message(rng: random.Random) -> str:
    return rng.choice(_CHAT)


def contract(rng: random.Random, clauses: int) -> str:
    parts = [f"MASTER SERVICES AGREEMENT between {rng.choice(COMPANIES)} and {rng.choice(COMPANIES)}."]
    for k in range(clauses):
        parts.append(f"{k + 1}. " + rng.choice(_CLAUSE).format(n=rng.randint(5, 90)))
    return "\n".join(parts)


def code_file(rng: random.Random, blocks: int) -> str:
    return "\n".join(rng.choice(_CODE) for _ in range(blocks))


def article(rng: random.Random, sentences: int) -> str:
    return " ".join(rng.choice(_ARTICLE) for _ in range(sentences))


def samples(seed: int = 7) -> dict[str, list[str]]:
    """A fixed corpus used by the words-to-tokens study."""
    rng = random.Random(seed)
    return {
        "chat": [chat_message(rng) for _ in range(200)],
        "contract": [contract(rng, rng.randint(20, 60)) for _ in range(40)],
        "code": [code_file(rng, rng.randint(10, 40)) for _ in range(40)],
        "article": [article(rng, rng.randint(10, 40)) for _ in range(40)],
    }
