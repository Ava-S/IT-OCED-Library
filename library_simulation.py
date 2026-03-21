from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import simpy
import random

from faker.providers.date_time import timestamp_to_datetime
from tqdm import tqdm as tqdm

log = []
violations = []
violation_counter = {'MISSING DELETE RELATION': 0, 'LIFETIME': 0, 'MISSING UPDATE': 0}
warm_up_phase = 100
start_recording = datetime(day=1, month=1, year=2025)
start_date = start_recording  - timedelta(days=warm_up_phase) # 50 days earlier

env = simpy.Environment()
verbose = False
opening_activities = ['Borrow book', 'Return book']
book_activities = ['Borrow book', 'Extend book', 'Return book', 'Reserve book', 'Remove Reservation',
                   'Add Book To Catalogue', 'Remove Book from Catalogue']
fine_activities = ['Increase fine', 'Pay fine']
member_activities = ['Register Member', 'Deregister Member']
automatic_activities = ['Increase fine', 'Remove Reservation', 'Add Book To Catalogue', 'Remove Book from Catalogue']
max_books_borrowed = 10

max_books = {
    "Budget": 2,
    "Comfort": 3,
    "Deluxe": 5
}

# Time constants in minutes (adjust if you simulate seconds)
OPEN_MIN = 8 * 60
CLOSE_MIN = 17 * 60
DAY = 24 * 60
THIRTY_DAYS = 30 * DAY  # minute


def truncated_exp_days(mean, low, high):
    x = round(random.expovariate(1 / mean))
    while not (low <= x <= high):
        x = round(random.expovariate(1 / mean))
    return x


def exp_days(mean):
    """Draw integer days from an exponential with given mean."""
    return max(0, round(random.expovariate(1 / float(mean))))


def get_jitter():
    return max(0.0, float(random.uniform(1, 10)))  # 1–10 minutes (for very small desyncs)


def wait_for_open(env, jitter_dist=None):
    """
    Wait until the library is open. If already open, return immediately.
    Optionally add a jitter after opening to avoid stampede at OPEN_MIN.
    `jitter_dist` is a callable that returns a non-negative delay (minutes).
    """
    now_in_day = env.now % DAY

    if OPEN_MIN <= now_in_day < CLOSE_MIN:
        # already open
        pass
    else:
        # time until next OPEN_MIN
        if now_in_day < OPEN_MIN:
            to_open = OPEN_MIN - now_in_day
        else:
            to_open = (DAY - now_in_day) + OPEN_MIN
        yield env.timeout(to_open)

    if jitter_dist is not None:
        jitter = max(0.0, float(jitter_dist()))
        if jitter > 0:
            yield env.timeout(jitter)


def small_uniform_jitter():
    return random.uniform(2, 20)  # spread first actions over 2–20 minutes


def short_exp_jitter(mean=5):
    return random.expovariate(1 / mean)


def random_datetime(date, last_date=None, activity: str = None):
    # check if last date is not given, or not on the same date
    if last_date is None or date.date() != last_date.date():
        start_date = date.replace(hour=8, minute=0, second=0)
        end_date = date.replace(hour=17, minute=0, second=0)
    else:  # last event happened on same day, if so, then start date should be at least equal to last date
        start_date = last_date
        if activity == "Pay fine":
            end_date = start_date + timedelta(minutes=10)
        else:
            end_date = start_date + timedelta(hours=1)
        # user can only do operations when library is open
        if end_date > date.replace(hour=17, minute=0, second=0) and activity in opening_activities:
            end_date = date.replace(hour=17, minute=0, second=0)

    delta = end_date - start_date
    int_delta = delta.seconds
    if end_date > start_date:
        random_second = random.randrange(int_delta)
    else:
        random_second = 0
    return start_date + timedelta(seconds=random_second)


class Entry:
    def __init__(self, timestamp, activity, member_id, registration_id, library, books=None, fine=None,
                 subscription_type=None, book_availability=None, book_reserved=None):
        self.timestamp = start_date + timedelta(minutes=timestamp)

        self.activity = activity

        self.member_id = member_id
        self.registration_id = registration_id
        self.books = books
        self.fine_amount = fine
        self.book_availability = book_availability
        self.book_reserved = book_reserved
        self.subscription_type = subscription_type
        self.library = library

        if self.activity in book_activities:
            self.origin = "Book"
        elif self.activity in fine_activities:
            self.origin = "Fine"
        else:
            self.origin = "Subscription"

    def get_book_by_index(self, index):
        if self.books is None:
            return None
        if index >= len(self.books):
            return None
        return self.books[index]

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "activity": self.activity,
            "member_id": self.member_id,
            "registration_id": self.registration_id,
            "origin": self.origin,
            "book_id1": self.get_book_by_index(0),
            "book_id2": self.get_book_by_index(1),
            "book_id3": self.get_book_by_index(2),
            "book_id4": self.get_book_by_index(3),
            "book_id5": self.get_book_by_index(4),
            "fine_amount": self.fine_amount,
            "subscription_type": self.subscription_type,
            "book_availability": self.book_availability,
            "book_reserved": self.book_reserved,
            "library": self.library
        }


class Book:
    def __init__(self, book_id, with_violations):
        self.book_id = book_id
        self.available = True
        self.borrower = None
        self.extend_count = 0
        self.last_borrowed = None
        self.reserved = False
        self.reserver = None
        self.last_reserved = None
        self.last_available = 0
        self.borrowed_counter = 0
        self.lifetime_violations = random.random() < .1 if with_violations else False #10% chance that book is borrowed too often
        self.max_borrowed = max_books_borrowed if not self.lifetime_violations else random.randint(11, 15)

    def __repr__(self):
        return self.book_id

    def reserved_by_someone_else(self, member):
        return self.reserved and self.reserver != member

    def add_borrowed(self):
        self.borrowed_counter += 1

    def can_be_borrowed(self):
        return self.borrowed_counter < self.max_borrowed

    def check_violating(self):
        if self.borrowed_counter > max_books_borrowed:
            violation_counter['LIFETIME'] += 1
            violations.append(f"LIFETIME VIOLATION: Book {self.book_id} is borrowed for the {self.borrowed_counter} time, violating lifetime constraints")

    def should_be_removed(self):
        if random.random() < .05:
            return self.available and self.max_borrowed <= self.borrowed_counter  # remove book if borrowed max_books
        else:
            return False


class Library:
    def __init__(self, env, library_name, members, catalogue, pbar, with_fine):
        self.env = env
        self.members = members
        self.library_name = library_name
        self.catalogue = catalogue
        self.not_in_catalogue = None
        self.removed_books = []
        self.create_initial_catalogue()
        self.action = env.process(self.run())
        self.with_fine = with_fine
        self.fine = env.process(self.update_day(pbar))

    def create_initial_catalogue(self):
        print(f"number of books: {len(self.catalogue)}")
        self.not_in_catalogue = random.sample(self.catalogue, round(len(self.catalogue) / 10))
        self.catalogue = [book for book in self.catalogue if book not in self.not_in_catalogue]

    def run(self):
        # wait for start of race
        yield self.env.timeout(0)
        for member in self.members:
            env.process(member.run(self.catalogue))

    def add_books_to_catalogue(self, now):
        num_to_add = random.randint(1, 50)
        num_to_add = min(num_to_add, len(self.not_in_catalogue))
        books_to_add = random.sample(self.not_in_catalogue, num_to_add)

        for book in books_to_add:
            if verbose:
                print(f"Add {book.bookid} book to catalogue of {self.library_name}")

            self.not_in_catalogue.remove(book)
            self.catalogue.append(book)
            entry = Entry(
                timestamp=now,
                member_id=None,
                registration_id=None,
                books=[book],
                activity="Add Book To Catalogue",
                library=self.library_name
            )
            log.append(entry)

    def remove_books_from_catalogue(self, now):
        num_to_remove = random.randint(1, 50)
        num_to_remove = min(num_to_remove, len(self.catalogue))
        books_to_remove = random.sample(self.catalogue, num_to_remove)

        for book in self.catalogue:
            if book.should_be_removed() and book not in books_to_remove:
                books_to_remove.append(book)

        for book in books_to_remove:
            if book.reserved or not book.available:
                continue  # book is popular, so not removed
            if verbose:
                print(f"Removed {book.bookid} book to catalogue of {self.library_name}")
            self.catalogue.remove(book)
            self.removed_books.append(book)
            entry = Entry(
                timestamp=now,
                member_id=None,
                registration_id=None,
                books=[book],
                activity="Remove Book from Catalogue",
                library=self.library_name
            )
            log.append(entry)

    def update_day(self, pbar):
        env = self.env
        first = True

        while True:
            if first:
                # Jump to first 23:59
                yield env.timeout(DAY - 1)
                first = False
            else:
                # Jump to next 23:59
                yield env.timeout(DAY)

            if random.random() < 0.02:
                self.add_books_to_catalogue(now=env.now)

            if random.random() < 0.02:
                self.remove_books_from_catalogue(now=env.now)

            for member in self.members:
                if self.with_fine:
                    member.increase_fine(now=env.now)
                member.automatic_remove_reservation(now=env.now)

            pbar.update(1)


class Member:
    def __init__(self, env, member, library, with_violations=False):
        self.env = env
        self.member_id = member['member_id']
        self.registration_id = member['registration_id']
        self.books_borrowed = []
        self.books_reserved = []
        self.fine = 0
        self.subscription_type = member['subscription_type']
        self.library = library
        self.is_member = random.random() < 0.98
        self.with_violations = with_violations

    def change_reserve(self, book, reserve=True):
        if reserve:
            book.reserved = True
            book.reserver = self
            book.last_reserved = env.now
            self.books_reserved.append(book)
            if verbose:
                print(
                    f"Member {self.member_id} has reserved {book.book_id} at library {self.library} at day {env.now}")
        else:
            book.reserved = False
            book.reserver = None
            book.last_reserved = None
            if book in self.books_reserved:
                self.books_reserved.remove(book)

    def change_extend(self, book):
        book.last_borrowed = env.now
        book.extend_count += 1

        if verbose:
            print(
                f"Member {self.member_id} extended Book {book.book_id} at library {self.library} at day {env.now}")

    def change_borrow(self, book, borrow=True):
        if borrow:
            book.available = False
            book.borrower = self
            book.last_borrowed = env.now
            book.last_available = None
            book.add_borrowed()
            book.check_violating()
            self.books_borrowed.append(book)
            if verbose:
                print(
                    f"Member {self.member_id} has borrowed {book.book_id} at library {self.library} at day "
                    f"{env.now}")
        else:
            book.available = True
            book.last_available = env.now
            book.borrower = None
            book.last_borrowed = None
            book.extend_count = 0
            if book in self.books_borrowed:
                self.books_borrowed.remove(book)
            if verbose:
                print(
                    f"Member {self.member_id} returned Book {book.book_id} at library {self.library} at day "
                    f"{env.now} ")

    def violate_fine_addition(self):
        if self.with_violations and random.random() < 0.001:
            if start_date + timedelta(minutes=env.now) > start_recording:
                violation_counter['MISSING UPDATE'] += 1
                violations.append(
                    f"MISSING UPDATE: Member {self.member_id} does not have an incurred different fine")
                return True
        return False



    def increase_fine(self, now):
        added_fine = 0
        for book in self.books_borrowed:
            if now - book.last_borrowed > THIRTY_DAYS:
                added_fine += .1
        if added_fine > 0:
            if verbose:
                print(f"Add {added_fine} cents fine to member {self.member_id}")
            if not self.violate_fine_addition():
                self.fine = round(self.fine + added_fine, ndigits=1)

            entry = Entry(
                timestamp=now,
                member_id=self.member_id,
                fine=self.fine,
                registration_id=self.registration_id,
                activity="Increase fine",
                library=self.library
            )
            log.append(entry)

    def automatic_remove_reservation(self, now):
        for book in self.books_reserved:
            if book.reserved and book.available and (env.now - book.last_reserved > THIRTY_DAYS):
                self.change_reserve(book, reserve=False)
                entry = Entry(
                    timestamp=now,
                    member_id=self.member_id,
                    fine=self.fine,
                    registration_id=self.registration_id,
                    activity="Remove Reservation",
                    books=[book],
                    library=self.library,
                    book_reserved=False
                )
                log.append(entry)

    def reserve_books(self, catalogue=None, num_books=0, books=None):
        env = self.env
        yield env.timeout(0)  # always a generator (safe)

        if books is not None:
            # Explicit book list from caller
            candidate_books = list(books)
        else:
            # Choose from catalogue
            reservable = [b for b in catalogue if not b.reserved]
            candidate_books = random.sample(
                reservable,
                min(num_books, len(reservable))
            )

        # Limit based on subscription
        max_allowed = max_books[self.subscription_type]
        free_slots = max_allowed - len(self.books_reserved)
        candidate_books = candidate_books[:free_slots]

        reserved_books = []
        for book in candidate_books:
            if not book.reserved and book.can_be_borrowed(): # book can still be borrowed
                self.change_reserve(book, reserve=True)
                reserved_books.append(book)

        # If nothing actually got reserved → exit early
        if not reserved_books:
            return

        entry = Entry(
            timestamp=env.now,
            member_id=self.member_id,
            fine=self.fine,
            registration_id=self.registration_id,
            activity="Reserve book",
            books=reserved_books,
            library=self.library,
            book_reserved=True
        )

        log.append(entry)
        yield env.timeout(get_jitter())

    def borrow_books(self, num_books_to_borrow, catalogue):
        env = self.env

        # 👇 ensure daytime only (with jitter to avoid 08:00 stampede)
        yield from wait_for_open(env, jitter_dist=small_uniform_jitter)

        # Determine how many we can borrow maximum
        available_books = [b for b in catalogue if b.available]
        num_books_to_borrow = min(num_books_to_borrow, len(available_books))

        max_allowed = max_books[self.subscription_type]
        can_borrow = max_allowed - len(self.books_borrowed)
        num_books_to_borrow = min(num_books_to_borrow, can_borrow)

        newly_borrowed = []
        reserved_borrowed = []
        reserved_not_available = []
        to_reserve = []

        def pick_reserved():
            """Try to take a reserved book (with failure chance)."""
            random.shuffle(self.books_reserved)
            book = self.books_reserved.pop(0)

            # small chance that reserved book is not picked up OR not actually available
            if random.random() < 0.05 or not book.available or not book.can_be_borrowed():
                reserved_not_available.append(book)
                return None
            # book is available and added to list to be borrowed
            self.change_reserve(book, reserve=False)
            reserved_borrowed.append(book)
            return book

        def pick_random():
            """Try to pick a random catalogue book (otherwise reserve it)."""
            book = random.choice([book for book in catalogue if book not in to_reserve])
            if book in to_reserve:
                return None
            if not book.available:
                to_reserve.append(book)
                return None
            if book.reserved_by_someone_else(member=self):
                return None
            if not book.can_be_borrowed():
                return None
            return book

        # ----- Borrow loop ----
        for _ in range(num_books_to_borrow):
            book = None
            while book is None:
                if self.books_reserved:  # try to borrow reserved books
                    book = pick_reserved()
                else:  # reserve a random book
                    book = pick_random()

            # Successfully borrow
            newly_borrowed.append(book)
            self.change_borrow(book, borrow=True)

        # return failed reserved items
        self.books_reserved.extend(reserved_not_available)

        # Reserve the unavailable ones
        if to_reserve:
            # reserve the non-available books
            self.reserve_books(books=to_reserve)
            jitter = get_jitter()
            if jitter > 0 and env.now + jitter < CLOSE_MIN:  # only jitter if we stay within the opening hours
                yield env.timeout(jitter)

        # Logging
        if newly_borrowed:
            entry = Entry(
                timestamp=env.now,
                member_id=self.member_id,
                fine=self.fine,
                registration_id=self.registration_id,
                activity="Borrow book",
                books=newly_borrowed,
                library=self.library,
                book_availability=False
            )

            log.append(entry)

            if reserved_borrowed:
                log.append(Entry(
                    timestamp=env.now,
                    member_id=self.member_id,
                    fine=self.fine,
                    registration_id=self.registration_id,
                    activity="Remove Reservation",
                    books=reserved_borrowed,
                    library=self.library,
                    book_reserved=False
                ))

        yield env.timeout(get_jitter())

    def pay_fine(self):
        """
        Attempt to pay a fine.
        - Only some attempts happen (70%).
        - If online is allowed and chosen, payment can happen anytime.
        - Otherwise, payment is restricted to opening hours (with jitter to avoid 08:00 clustering).
        - Always returns a generator (safe for env.process()).
        """
        env = self.env

        # Ensure this is always a generator even if we exit early
        # by adding a zero-duration yield at the top.
        yield env.timeout(0)

        # Branch: online vs in-person
        online = (random.random() < 0.5)

        if not online:
            # Only during opening hours (with jitter)
            yield from wait_for_open(env, jitter_dist=small_uniform_jitter)

        # Finalize payment
        amount_paid = self.fine
        self.fine = 0

        if verbose:
            mode = "online" if online else "at library"
            print(f"Member {self.member_id} paid fine ({mode}) at {self.library}: "
                  f"{amount_paid} at t={env.now}.")

        entry = Entry(
            timestamp=env.now,
            member_id=self.member_id,
            fine=0,  # current balance after paying
            registration_id=self.registration_id,
            activity="Pay fine",
            library=self.library
        )
        log.append(entry)

        yield env.timeout(get_jitter())

    def extend_books(self):
        """
            Extend borrowed books.
            - Most  extensions happen online (24/7).
            - Others require the library to be open.
            - Always yields once (safe to use in env.process).
        """
        env = self.env

        # Always be a generator
        yield env.timeout(0)

        # determine if this extension is online
        is_online = (random.random() < 0.7)

        # If extension must be done in-person → wait until opening
        if not is_online:
            yield from wait_for_open(env, jitter_dist=small_uniform_jitter)

        # Collect extendable books
        extendable_books = [b for b in self.books_borrowed if not b.reserved and b.extend_count < 3]

        if not extendable_books:
            return  # nothing to extend; already yielded above

        # Perform the extensions
        for book in extendable_books:
            self.change_extend(book=book)

        # Logging
        entry = Entry(
            timestamp=env.now,
            member_id=self.member_id,
            fine=self.fine,
            registration_id=self.registration_id,
            activity="Extend book",
            books=extendable_books,
            library=self.library
        )

        log.append(entry)

        yield env.timeout(get_jitter())

    def return_books(self):
        env = self.env
        yield env.timeout(0)  # always generator

        if not self.books_borrowed:  # no books are borrowed
            return

        # 👇 ensure daytime only (with jitter to avoid 08:00 stampede)
        yield from wait_for_open(env, jitter_dist=small_uniform_jitter)

        # determine which books to return
        returned_books = []

        # ensure that at least one book is return
        forced_book = random.choice(self.books_borrowed)

        for book in self.books_borrowed:
            if random.random() < 0.85 or book == forced_book:
                self.change_borrow(book, borrow=False)
                returned_books.append(book)

        # Logging
        entry = Entry(
            timestamp=env.now,
            member_id=self.member_id,
            fine=self.fine,
            registration_id=self.registration_id,
            activity="Return book",
            books=returned_books,
            library=self.library,
            book_availability=True
        )

        if self.with_violations and random.random() < 0.99:  # in most cases, add the event
            log.append(entry)
        else:
            if entry.timestamp > start_recording:
                for book in self.books_borrowed:
                    violations.append(f'MISSING DELETE RELATION Return Book Event for books {book.book_id}')
                    violation_counter['MISSING DELETE RELATION'] += 1

        yield env.timeout(get_jitter())

    def update_subscription_type(self):
        subscription_types = [x for x in ["Budget", "Comfort", "Deluxe"] if x != self.subscription_type]
        self.subscription_type = random.choice(subscription_types)
        entry = Entry(
            timestamp=env.now,
            member_id=self.member_id,
            fine=self.fine,
            registration_id=self.registration_id,
            activity="Update Subscription Type",
            subscription_type=self.subscription_type,
            library=self.library
        )
        log.append(entry)
        yield env.timeout(0)

    def register_member(self):
        env = self.env
        yield env.timeout(0)  # always generate
        self.is_member = True

        entry = Entry(
            timestamp=env.now,
            member_id=self.member_id,
            fine=self.fine,
            registration_id=self.registration_id,
            activity="Register Member",
            subscription_type=self.subscription_type,
            library=self.library
        )
        log.append(entry)

    def deregister_member(self):
        env = self.env
        yield env.timeout(0)  # always generate

        # Member is now deregistered
        self.is_member = False
        entry = Entry(
            timestamp=env.now,
            member_id=self.member_id,
            fine=self.fine,
            registration_id=self.registration_id,
            activity="Deregister Member",
            subscription_type=self.subscription_type,
            library=self.library
        )
        log.append(entry)

        # Remove reservations
        for book in list(self.books_reserved):
            self.change_reserve(book, reserve=False)
            entry = Entry(
                timestamp=env.now,
                member_id=self.member_id,
                fine=self.fine,
                registration_id=self.registration_id,
                activity="Remove Reservation",
                books=[book],
                library=self.library,
                book_reserved=False
            )

            log.append(entry)

        # Assign new subscription type if they rejoin later
        self.registration_id += 1
        self.subscription_type = random.choice(["Budget", "Comfort", "Deluxe"])

    def wait_member_delay(self, context="generic"):
        """
        Delay until the NEXT member action.
        - context: "generic", "after_borrow", "after_return", "after_extend", "after_reserve",
                   "after_register", "after_deregister"
        - offline: if True, align the wake-up to opening hours (with jitter)
        Times are drawn in DAYS, converted to minutes.
        """
        env = self.env

        # --- Choose a mean in DAYS based on context & state ---
        has_books = len(self.books_borrowed) > 0

        # Base means (tune to your data):
        means = {
            ("generic", False): 40,  # no books: ~once every 40 days
            ("generic", True): 25,  # has books: ~every 25 days

            ("after_register", False): 0,  # immediate borrow books

            ("after_deregister", False): 60,  # reconsider after 60 days
        }

        key = (context, has_books)
        mean_days = means.get(key, 14)

        # Draw delay (in days), add small fractional-day jitter
        if mean_days > 0:
            days = exp_days(mean_days)
        else:
            days = 0

        jitter_minutes = random.uniform(15, 6 * 60)  # 15 min – 6 hours

        total_minutes = days * DAY + jitter_minutes

        # Just wait the total minutes
        yield env.timeout(total_minutes)

    def inactive_period(self):
        env = self.env

        if len(self.books_borrowed) > 0:
            inactive_days = round(random.expovariate(1 / 14))  # mean = 14 days
        else:
            inactive_days = round(random.expovariate(1 / 50))  # mean = 50 days

        # Convert to minutes
        inactive_minutes = inactive_days * DAY
        # # Add jitter (15 min to 5 hours)
        jitter = float(random.uniform(15, 5 * 60))
        total_inactive = max(0.0, inactive_minutes + jitter)

        if verbose:
            print(
                f"Member {self.member_id} has inactive period at library {self.library} of {total_inactive} minutes")

        yield env.timeout(total_inactive)

    def run(self, catalogue):
        env = self.env
        first = True
        while True:

            # -----------------------------------------
            # FIRST CONTACT
            # -----------------------------------------
            if first:
                yield env.process(self.inactive_period())
                first = False
                if not self.is_member:
                    yield env.process(self.register_member())
                    yield env.process(self.wait_member_delay(context='after_register'))

            # -----------------------------------------
            # RANDOM DEREGISTRATION EVENT
            # -----------------------------------------
            if random.random() < 0.02 and self.is_member:  # deregister as member
                if self.fine > 0:
                    yield env.process(self.pay_fine())
                yield env.process(self.deregister_member())
                yield env.process(self.wait_member_delay(context='after_deregister'))
                continue

            # -----------------------------------------
            # NON-MEMBER BEHAVIOR --> try to become member
            # -----------------------------------------
            if not self.is_member:
                if random.random() < 0.15:
                    yield env.process(self.register_member())
                    yield env.process(self.wait_member_delay(context='after_register'))
                else:
                    yield env.process(self.wait_member_delay(context='after_deregister'))
                continue

            if self.is_member:  # Active but no books → do other member actions
                chance = random.random()
                if chance < 0.70:
                    yield env.process(self.borrow_books(random.randint(1, 5), catalogue))
                elif chance < 0.90:
                    yield env.process(self.reserve_books(catalogue, num_books=random.randint(1, 5)))

                # Pay fine
                if self.fine > 0 and random.random() < 0.7:
                    yield env.process(self.pay_fine())

                # wait member behavior
                yield env.process(self.wait_member_delay())

            # ----------------------------------------------------------
            # MEMBER BEHAVIOR: RETURN LOOP (this controls loan duration) --> we still have borrowed books
            # ----------------------------------------------------------
            while len(self.books_borrowed) > 0:
                # RETURN event includes timing:
                if random.random() < 0.90:
                    yield env.process(self.return_books())
                    returned = True
                else:
                    yield env.process(self.extend_books())
                    returned = False

                # Pay fine
                if self.fine > 0 and random.random() < 0.7:
                    yield env.process(self.pay_fine())

                # AFTER RETURN, DECIDE NEXT ACTION
                if len(self.books_borrowed) > 0 and random.random() < 0.8 and returned:
                    # EXTEND resets loan period
                    yield env.process(self.extend_books())

                if random.random() < 0.75:  # borrow new books
                    yield env.process(self.borrow_books(random.randint(1, 5), catalogue))

                # wait member behavior
                yield env.process(self.wait_member_delay())


class Simulation:
    def __init__(self, library_data, simulation_days, with_fine=True):
        self.library_data = library_data

        # self.books = [Book(book_id=book) for book in book_ids]
        # self.members = [Member(env, member_id) for member_id in member_ids]
        self.simulation_duration = (simulation_days + warm_up_phase + 10) * DAY
        self.env = env
        self.with_fine = with_fine

    def create_library_instance(self, pbar, with_violations):
        instances = []
        for library_name, library_data in self.library_data.items():
            books = [Book(book_id=book, with_violations=with_violations) for book in library_data["books"]]
            members = [Member(env, member, library_name, with_violations=with_violations) for member in library_data["members"]]
            library = Library(env, library_name, members, books, pbar, self.with_fine)
            instances.append(library)
        return instances

    def run(self, end_year = 2026, with_violations=False):
        pbar = tqdm(total=self.simulation_duration * len(self.library_data) / DAY)
        libraries = self.create_library_instance(pbar, with_violations = with_violations)
        env.run(until=self.simulation_duration)

        event_log_df = pd.DataFrame([event.to_dict() for event in log])
        if not self.with_fine:
            event_log_df.drop(columns=["new_fine_amount"], inplace=True)

        event_log_df = event_log_df[event_log_df['timestamp'] >= start_recording]
        event_log_df = event_log_df[event_log_df['timestamp'] < datetime(day=1, month=1, year=end_year)]

        event_log_df.to_csv(Path('data/event_log_with_reserve.csv'), index=False)
        if with_violations:
            violations_df = pd.DataFrame(violations)
            violations_df.to_csv(Path('data/injected_violations.csv'), index=False)

        print(f'Finished')
        print(f'Inserted the following number of violations: {violation_counter}')
        pbar.close()
