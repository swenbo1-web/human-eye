"""Small, synchronized in-memory reservation ledger owned by one trusted runner.

One instance must be shared by every formal episode in the run. It never reads
credentials, requests balances/prices, persists data, or contacts a provider.
Reservations are conservative and nonrefundable, including failed/unknown calls.
Amounts use decimal arithmetic so independently rounded episode totals cannot
reuse the global allowance. This is not an accounting or billing service.
"""
from __future__ import annotations

import math
import threading
from decimal import Decimal, localcontext


class SpendRejected(ValueError):
    pass


def _amount(value, name):
    if type(value) not in (int, float):
        raise SpendRejected(name + ' must be an explicit finite numeric amount')
    try:
        valid = math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise SpendRejected(name + ' must be finite and nonnegative')
    return Decimal(str(value))


def _identity(value, name):
    if type(value) is not str or not value.strip() or len(value) > 256:
        raise SpendRejected(name + ' must be a nonempty bounded identity')
    return value


def _add(left, right):
    # All accepted finite float/int magnitudes fit within ~633 decimal places.
    # Use a local context so tiny positive reservations never round away beside
    # a large cap, and other threads' Decimal settings cannot change this gate.
    with localcontext() as context:
        context.prec = 1024
        return left + right


class SharedRunBudget:
    """Run-wide cap and at most 36 unique episode admissions.

    The runner supplies verified conservative fee and balance bounds. Until
    balance settlements can be reconciled, the smallest supplied balance is a
    ceiling for *all* retained reservations; a later balance cannot replenish the
    ledger. This deliberately conservative rule also prevents two threads from
    spending the same stale balance snapshot. No refund/release API exists.
    """

    def __init__(self, cap, currency, max_episodes=36):
        amount = _amount(cap, 'cap')
        if amount <= 0:
            raise SpendRejected('run cap must be positive')
        if (type(currency) is not str or not currency.strip() or len(currency) > 32):
            raise SpendRejected('currency must be explicitly bound')
        if type(max_episodes) is not int or not 1 <= max_episodes <= 36:
            raise SpendRejected('max_episodes must be an integer in 1..36')
        self._cap = amount
        self._currency = currency
        self._max_episodes = max_episodes
        self._lock = threading.RLock()
        self._episodes = {}
        self._reservations = {}
        self._seen_reservation_ids = set()
        self._reserved = Decimal('0')
        self._balance_ceiling = None

    @property
    def cap(self):
        return self._cap

    @property
    def currency(self):
        return self._currency

    @property
    def max_episodes(self):
        return self._max_episodes

    @property
    def total_reserved(self):
        with self._lock:
            return self._reserved

    def matches_binding(self, cap, currency):
        return self._cap == _amount(cap, 'binding total cap') and self._currency == currency

    def claim_episode(self, episode_id):
        identity = _identity(episode_id, 'episode_id')
        with self._lock:
            if identity in self._episodes:
                raise SpendRejected('episode identity cannot be reused in this run')
            if len(self._episodes) >= self._max_episodes:
                raise SpendRejected('global episode count exhausted')
            self._episodes[identity] = {'reserved': Decimal('0'), 'requests': 0}
            return self._snapshot()

    def reserve(self, episode_id, reservation_id, cost_upper_bound,
                balance_available, currency):
        episode = _identity(episode_id, 'episode_id')
        identity = _identity(reservation_id, 'reservation_id')
        amount = _amount(cost_upper_bound, 'cost upper bound')
        balance = _amount(balance_available, 'verified balance')
        if currency != self._currency:
            raise SpendRejected('reservation currency differs from the run binding')
        with self._lock:
            if episode not in self._episodes:
                raise SpendRejected('episode must be admitted before reserving a request')
            if identity in self._seen_reservation_ids:
                raise SpendRejected('request reservation identity cannot be reused')
            # Even a rejected reservation attempt cannot be replayed under an
            # ambiguous ID. A new attempt requires a new trusted adapter ID.
            self._seen_reservation_ids.add(identity)
            ceiling = balance if self._balance_ceiling is None else min(self._balance_ceiling, balance)
            self._balance_ceiling = ceiling
            proposed = _add(self._reserved, amount)
            if proposed > self._cap:
                raise SpendRejected('run-wide conservative cost cap would be exceeded')
            if proposed > ceiling:
                raise SpendRejected('run-wide retained reservations exceed verified balance ceiling')
            self._reserved = proposed
            self._episodes[episode]['reserved'] = _add(self._episodes[episode]['reserved'], amount)
            self._episodes[episode]['requests'] += 1
            receipt = {'episode_id': episode, 'reservation_id': identity,
                       'cost_upper_bound': str(amount), 'currency': self._currency,
                       'run_reserved_total': str(self._reserved),
                       'verified_balance_ceiling': str(ceiling),
                       'status': 'retained_nonrefundable'}
            self._reservations[identity] = receipt
            return dict(receipt)

    def _snapshot(self):
        return {'scope': 'entire_run', 'cap': str(self._cap), 'currency': self._currency,
                'max_episodes': self._max_episodes, 'admitted_episodes': len(self._episodes),
                'reserved_requests': len(self._reservations),
                'seen_reservation_ids': len(self._seen_reservation_ids),
                'reserved_total': str(self._reserved), 'remaining_cap': str(_add(self._cap, self._reserved.copy_negate())),
                'verified_balance_ceiling': None if self._balance_ceiling is None else str(self._balance_ceiling),
                'refunds_supported': False}

    def snapshot(self):
        with self._lock:
            return self._snapshot()
