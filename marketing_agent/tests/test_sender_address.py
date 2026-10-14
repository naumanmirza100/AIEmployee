"""The address the inbox reader takes out of a From or To line.

It kept the first thing in the line that looked like letters@letters, allowing
only letters, digits, dots and hyphens before the @. An address with a plus sign
or an apostrophe was cut short into somebody else's mailbox, and a display name
that was itself an address was stored in place of the real sender. Reply Draft
sends the approved reply to the stored address, and campaign reply matching uses
it too.
"""
import base64
import email
from email.header import Header

from django.test import SimpleTestCase

from marketing_agent.management.commands.sync_inbox import Command


def encoded(text):
    return '=?utf-8?b?' + base64.b64encode(text.encode()).decode() + '?='


class SenderAddressTests(SimpleTestCase):

    def address(self, header):
        return Command().get_email_address(header)

    def test_the_address_part_is_kept_whole(self):
        for header, expected in {
            'Mary Khan <mary+work@gmail.com>': 'mary+work@gmail.com',
            "o'brien@firm.com": "o'brien@firm.com",
            "Sean O'Brien <o'brien@firm.com>": "o'brien@firm.com",
            'first_last@firm.com': 'first_last@firm.com',
            'a!b#c$d%e&f*g/h=i?j^k{l|m}n~o@firm.com': 'a!b#c$d%e&f*g/h=i?j^k{l|m}n~o@firm.com',
            'plain@example.com': 'plain@example.com',
            '<plain@example.com>': 'plain@example.com',
            'Plain Person <Plain.Person@Example.COM>': 'plain.person@example.com',
        }.items():
            self.assertEqual(self.address(header), expected, header)

    def test_a_display_name_that_looks_like_an_address_is_not_the_address(self):
        self.assertEqual(self.address('"billing@bank.com" <someone@else.com>'), 'someone@else.com')
        self.assertEqual(self.address('billing@bank.com <someone@else.com>'), 'someone@else.com')

    def test_a_display_name_in_another_alphabet_is_fine(self):
        self.assertEqual(self.address(encoded('علی احمد') + ' <ali@firm.com>'), 'ali@firm.com')

    def test_an_encoded_display_name_cannot_put_its_own_address_first(self):
        header = encoded('<billing@bank.com>') + ' <someone@else.com>'
        self.assertEqual(self.address(header), 'someone@else.com')
        header = encoded('billing@bank.com, x') + ' <someone@else.com>'
        self.assertEqual(self.address(header), 'someone@else.com')
        # With no brackets of its own in the header, brackets hidden in the name are not trusted either.
        self.assertNotEqual(self.address(encoded('<billing@bank.com>') + ' someone@else.com'), 'billing@bank.com')

    def test_the_header_as_the_mail_library_hands_it_over(self):
        message = email.message_from_string('From: Mary Khan <mary+work@gmail.com>\nTo: a@b.com\n\nHi')
        self.assertEqual(self.address(message.get('From', '')), 'mary+work@gmail.com')
        self.assertEqual(self.address(message['From']), 'mary+work@gmail.com')
        self.assertEqual(self.address(Header('Mary Khan <mary+work@gmail.com>')), 'mary+work@gmail.com')

    def test_a_folded_header_and_several_recipients(self):
        self.assertEqual(self.address('Mary Khan\r\n <mary+work@gmail.com>'), 'mary+work@gmail.com')
        self.assertEqual(self.address('First <first@firm.com>, Second <second@firm.com>'), 'first@firm.com')

    def test_nothing_usable_gives_nothing(self):
        for header in ('', None, 'Undisclosed recipients:;', 'just some words', 'half@', '@half.com',
                       'no-dot@localhost'):
            self.assertIsNone(self.address(header), header)
