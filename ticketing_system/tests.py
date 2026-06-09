from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from UserProfile.models import UserProfile
from ticketing_system.models import Category, Ticket, TicketMessage
from ticketing_system.rag_pipeline import _get_resolution_message, process_new_ticket_for_rag


class ResolutionMessageSelectionTests(TestCase):
    def _profile(self, username, role):
        user = User.objects.create_user(username, password='pass')
        profile = user.profile
        profile.role = role
        profile.save(update_fields=['role'])
        return profile

    def setUp(self):
        self.category = Category.objects.create(name='Technical Support')
        self.customer = self._profile('customer', 'Customer')
        self.agent = self._profile('agent', 'Agent')
        self.supervisor = self._profile('achraf', 'Supervisor')
        self.ai_agent = self._profile('ai_agent', 'AI_Agent')

    def _closed_ticket(self, title):
        return Ticket.objects.create(
            customer=self.customer,
            title=title,
            status='Closed',
            category=self.category,
        )

    def test_prefers_last_supervisor_message_over_earlier_agent(self):
        ticket = self._closed_ticket('VPN Fail')
        TicketMessage.objects.create(ticket=ticket, sender=self.customer, message='Cannot connect to VPN.')
        TicketMessage.objects.create(
            ticket=ticket, sender=self.agent, message='Checking your account settings.'
        )
        TicketMessage.objects.create(
            ticket=ticket,
            sender=self.supervisor,
            message='Restart your router and check your credentials.',
        )

        resolution = _get_resolution_message(ticket)
        self.assertEqual(resolution.sender.role, 'Supervisor')
        self.assertEqual(resolution.message, 'Restart your router and check your credentials.')

    def test_prefers_human_agent_over_ai_agent(self):
        ticket = self._closed_ticket('VPN Fail')
        TicketMessage.objects.create(ticket=ticket, sender=self.customer, message='VPN broken.')
        TicketMessage.objects.create(
            ticket=ticket, sender=self.ai_agent, message='Try rebooting your machine.'
        )
        TicketMessage.objects.create(
            ticket=ticket, sender=self.agent, message='Credentials were expired; reset sent.'
        )

        resolution = _get_resolution_message(ticket)
        self.assertEqual(resolution.sender.role, 'Agent')
        self.assertEqual(resolution.message, 'Credentials were expired; reset sent.')

    def test_falls_back_to_ai_agent_when_no_human_replied(self):
        ticket = self._closed_ticket('VPN Fail')
        TicketMessage.objects.create(ticket=ticket, sender=self.customer, message='VPN broken.')
        TicketMessage.objects.create(
            ticket=ticket, sender=self.ai_agent, message='Auto-resolved via prior ticket.'
        )

        resolution = _get_resolution_message(ticket)
        self.assertEqual(resolution.sender.role, 'AI_Agent')
        self.assertEqual(resolution.message, 'Auto-resolved via prior ticket.')

    def test_returns_none_when_only_customer_messages_exist(self):
        ticket = self._closed_ticket('VPN Fail')
        TicketMessage.objects.create(ticket=ticket, sender=self.customer, message='Still broken.')

        self.assertIsNone(_get_resolution_message(ticket))

    @patch('ticketing_system.rag_pipeline.generate_llm_response')
    def test_auto_resolve_uses_supervisor_message_verbatim(self, mock_llm):
        closed = self._closed_ticket('VPN Fail')
        TicketMessage.objects.create(
            ticket=closed,
            sender=self.customer,
            message='Cannot connect to VPN.',
        )
        TicketMessage.objects.create(
            ticket=closed,
            sender=self.supervisor,
            message='Restart your router and check your credentials.',
        )

        new_ticket = Ticket.objects.create(
            customer=self.customer,
            title='VPN Fail',
            status='Open',
            category=self.category,
        )
        TicketMessage.objects.create(
            ticket=new_ticket,
            sender=self.customer,
            message='Cannot connect to VPN again.',
        )

        process_new_ticket_for_rag(new_ticket)

        mock_llm.assert_not_called()
        new_ticket.refresh_from_db()
        self.assertEqual(new_ticket.status, 'Closed')
        reply = new_ticket.messages.exclude(sender=self.customer).last()
        self.assertEqual(reply.message, 'Restart your router and check your credentials.')
