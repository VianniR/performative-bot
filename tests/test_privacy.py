"""Offline regressions: no real DB, dotenv credentials, Discord login, or API calls."""
import os
import socket
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

# Prevent dotenv from loading private local configuration in this test process.
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['DB_URL'] = 'sqlite:///:memory:'
os.environ['DISCORD_BOT_TOKEN'] = 'test-key'
os.environ.pop('OPENAI_API_KEY', None)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.bot.db import initialize_database
from src.bot.models import User, Message, ChannelConfig, Score
from src.bot import scoring
from src.bot import bot as app


class DatabaseTests(unittest.TestCase):
    def test_legacy_migration_and_restart_preserve_all_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            url = f'sqlite:///{directory}/test.db'
            engine = create_engine(url)
            with engine.begin() as conn:
                conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, opted_in BOOLEAN NOT NULL, created_at TIMESTAMP NOT NULL, last_seen_at TIMESTAMP NOT NULL)'))
                conn.execute(text("INSERT INTO users VALUES (1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
            initialize_database(engine)
            factory = sessionmaker(bind=engine)
            with factory() as session:
                user = session.get(User, 1)
                self.assertTrue(user.opted_in)
                self.assertIsNone(user.consented_at)
                session.add(Message(user_id=1, channel_id=10, text='synthetic record'))
                session.add(Score(user_id=1, window_days=14, score=99, breakdown={'examples': ['synthetic legacy']}))
                session.add(ChannelConfig(channel_id=10, allowed=True))
                session.commit()
            engine.dispose()
            engine = create_engine(url)
            initialize_database(engine)
            initialize_database(engine)
            with sessionmaker(bind=engine)() as session:
                self.assertEqual(session.query(User).count(), 1)
                self.assertEqual(session.query(Message).one().text, 'synthetic record')
                self.assertEqual(session.query(Score).one().score, 99)
                self.assertTrue(session.get(ChannelConfig, 10).allowed)
            engine.dispose()

    def test_import_has_no_database_or_network_side_effects(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'never-created.db'
            env = dict(os.environ, DB_URL=f'sqlite:///{db}')
            subprocess.run([sys.executable, '-c', '''
from unittest.mock import patch
with patch('socket.socket.connect', side_effect=AssertionError('network forbidden')):
    from src.bot import bot
    assert {'optin', 'optout', 'meter', 'leaderboard', 'why'}.issubset({c.name for c in bot.tree.get_commands()})
'''], check=True, env=env)
            self.assertFalse(db.exists())

    def test_entrypoint_initializes_without_connecting(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'startup.db'
            env = dict(os.environ, DB_URL=f'sqlite:///{db}')
            subprocess.run([sys.executable, '-c', """
import runpy
from unittest.mock import patch
with patch('socket.socket.connect', side_effect=AssertionError('network forbidden')):
    with patch('discord.Client.run') as login:
        runpy.run_module('src.bot.bot', run_name='__main__')
        login.assert_called_once_with('test-key')
"""], check=True, env=env)
            self.assertTrue(db.exists())


class ConsentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        initialize_database(self.engine)
        self.factory = sessionmaker(bind=self.engine)
        self.sessions = patch.object(app, 'SessionLocal', self.factory)
        self.sessions.start()
        self.api = patch.object(scoring, 'analyze_message_with_chatgpt', return_value=1)
        self.analyze = self.api.start()
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden'))
        self.network.start()
        with self.factory() as session:
            session.add(ChannelConfig(channel_id=10, allowed=True))
            session.commit()

    def tearDown(self):
        self.network.stop()
        self.api.stop()
        self.sessions.stop()
        self.engine.dispose()

    def interaction(self, uid=1):
        channel = NS(id=10, permissions_for=lambda _: NS(view_channel=True, read_message_history=True))
        return NS(user=NS(id=uid), guild_id=100, guild=NS(channels=[channel], members=[]),
                  response=NS(send_message=AsyncMock(), defer=AsyncMock()), followup=NS(send=AsyncMock()))

    def message(self, uid=1, channel=10, **kwargs):
        return NS(author=NS(id=uid, bot=False), guild=NS(id=100), webhook_id=None,
                  channel=NS(id=channel), content='matcha https://open.spotify.com/test?private=example',
                  attachments=[], reactions=[], **kwargs)

    async def test_no_consent_or_legacy_flag_does_not_track_or_call_api(self):
        await app.on_message(self.message())
        with self.factory() as session:
            self.assertEqual(session.query(User).count(), 0)
            session.add(User(id=1, opted_in=True))
            session.commit()
        await app.on_message(self.message())
        with self.factory() as session:
            self.assertEqual(session.query(Message).count(), 0)
            self.assertEqual(scoring.compute_user_score_chatgpt(session, 1, channel_ids=[10])[0], 0)
        self.analyze.assert_not_called()

    async def test_optin_collection_optout_and_reoptin(self):
        interaction = self.interaction()
        await app.optin.callback(interaction)
        await app.on_message(self.message())
        await app.on_message(self.message(channel=99))
        with self.factory() as session:
            row = session.query(Message).one()
            self.assertEqual(row.links, ['https://open.spotify.com'])
            self.assertIsNone(session.get(User, 1).username)
            score, info = scoring.compute_user_score_chatgpt(session, 1, channel_ids=[10])
            self.assertEqual(score, 51.5)
            self.assertFalse(info['examples'])
        await app.optout.callback(interaction)
        self.analyze.reset_mock()
        await app.on_message(self.message())
        with self.factory() as session:
            self.assertEqual(session.query(Message).count(), 1)
            self.assertFalse(session.get(User, 1).opted_in)
            self.assertEqual(scoring.compute_user_score_chatgpt(session, 1, channel_ids=[10])[0], 0)
            self.assertEqual(scoring.compute_user_score(session, 1, channel_ids=[10])[0], 0)
        self.analyze.assert_not_called()
        await app.optin.callback(interaction)
        with self.factory() as session:
            self.assertEqual(scoring.compute_user_score_chatgpt(session, 1, channel_ids=[10])[0], 0)
        interaction.response.send_message.assert_awaited()

    async def test_server_consent_and_window_scope_ignore_legacy_cache(self):
        now = datetime.utcnow()
        with self.factory() as session:
            session.add(User(id=1, opted_in=True, consented_at=now-timedelta(days=20)))
            for channel, age, content in [(10, 1, 'visible'), (20, 1, 'other server'),
                                          (10, 21, 'before consent'), (10, 15, 'outside window')]:
                session.add(Message(user_id=1, channel_id=channel, created_at=now-timedelta(days=age), text=content))
            session.add(Score(user_id=1, window_days=14, score=99, breakdown={'examples': ['private']}))
            session.commit()
            score, info = scoring.compute_user_score_chatgpt(session, 1, channel_ids=[10])
            self.assertEqual(score, 51.5)
            self.assertEqual(info['total_messages'], 1)
            self.analyze.assert_called_once_with('visible')
            self.assertEqual(session.query(Score).one().score, 99)
            self.assertEqual(scoring.compute_user_score_chatgpt(session, 1)[0], 0)

    async def test_command_privacy_and_leaderboard_consent(self):
        await app.optin.callback(self.interaction())
        await app.on_message(self.message())
        with self.factory() as session:
            session.add(User(id=2, opted_in=False))
            session.add(Message(user_id=2, channel_id=10, text='excluded'))
            session.commit()
        interaction = self.interaction()
        interaction.guild.members = [NS(id=1, bot=False, display_name='Alice'), NS(id=2, bot=False, display_name='Bob')]
        await app.leaderboard.callback(interaction)
        result = interaction.followup.send.call_args.args[0]
        self.assertIn('Alice', result)
        self.assertNotIn('Bob', result)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        for command in (app.meter, app.why):
            interaction = self.interaction()
            await command.callback(interaction, NS(id=1, display_name='Alice'))
            self.assertNotIn('matcha', str(interaction.followup.send.call_args))
            interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    async def test_private_channels_and_disabled_channels_excluded(self):
        interaction = self.interaction()
        hidden = NS(id=20, permissions_for=lambda _: NS(view_channel=False, read_message_history=False))
        interaction.guild.channels.append(hidden)
        with self.factory() as session:
            session.add(ChannelConfig(channel_id=20, allowed=True))
            session.commit()
            self.assertEqual(app.scoring_channels(session, interaction), [10])
        await app.deny_channel.callback(NS(channel=NS(id=10, mention='test'), response=NS(send_message=AsyncMock())))
        with self.factory() as session:
            self.assertEqual(app.scoring_channels(session, interaction), [])

    async def test_sample_limit_formula_and_fallback(self):
        await app.optin.callback(self.interaction())
        for _ in range(12):
            await app.on_message(self.message())
        with self.factory() as session:
            score, info = scoring.compute_user_score_chatgpt(session, 1, channel_ids=[10])
            self.assertEqual(score, 65)
            self.assertEqual(self.analyze.call_count, 10)
            self.assertEqual(info['total_messages'], 12)
            self.analyze.return_value = None
            score, info = scoring.compute_user_score_chatgpt(session, 1, channel_ids=[10])
            self.assertIn('fallback', info['chatgpt_analysis'])
            self.assertTrue(0 <= score <= 100)

    async def test_command_errors_do_not_log_sensitive_details(self):
        interaction = self.interaction()
        interaction.response.is_done = lambda: False
        with self.assertLogs(app.__name__, level='WARNING') as logs:
            await app.command_error(interaction, app.app_commands.AppCommandError('sensitive fake payload'))
        self.assertNotIn('sensitive', str(logs.output))
        self.assertNotIn('sensitive', str(interaction.response.send_message.call_args))

    async def test_config_overrides_do_not_cross_servers(self):
        from src.bot.config import get_config, set_config_key
        with self.factory() as session:
            set_config_key('weights', {'text_vibe': 1}, session, guild_id=100)
            self.assertEqual(get_config(session, guild_id=100)['weights'], {'text_vibe': 1})
            self.assertNotEqual(get_config(session, guild_id=200)['weights'], {'text_vibe': 1})


class ApiTests(unittest.TestCase):
    def test_model_mapping_payload_and_redacted_errors(self):
        with patch.dict(os.environ, OPENAI_API_KEY='test-key', OPENAI_MODEL='test-model'):
            with patch.object(scoring.openai, 'OpenAI') as factory:
                client = factory.return_value
                for label, expected in [('PERFORMATIVE', 1), ('NON-PERFORMATIVE', -1), ('NEUTRAL', 0)]:
                    client.chat.completions.create.return_value = NS(choices=[NS(message=NS(content=label))])
                    self.assertEqual(scoring.analyze_message_with_chatgpt('synthetic text', 'private-name'), expected)
                args = client.chat.completions.create.call_args.kwargs
                self.assertEqual(args['model'], 'test-model')
                self.assertFalse(args['store'])
                self.assertNotIn('private-name', str(args))
                client.chat.completions.create.side_effect = RuntimeError('sensitive fake error')
                with patch('builtins.print') as output:
                    self.assertIsNone(scoring.analyze_message_with_chatgpt('synthetic text'))
                    output.assert_not_called()
                self.assertEqual(scoring.analyze_message_with_chatgpt('fraternity'), -1)


if __name__ == '__main__':
    unittest.main()
