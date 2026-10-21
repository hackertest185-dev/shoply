import test from 'node:test';
import assert from 'node:assert/strict';
import { getPasswordFeedback } from '../src/utils/passwordPolicy.js';

test('explains missing symbols and rejects common passwords with symbols', () => {
  assert.equal(getPasswordFeedback('MapleRiver123').ready, false);
  assert.match(getPasswordFeedback('MapleRiver123').message, /symbol/);
  assert.equal(getPasswordFeedback('Password123!').ready, false);
  assert.equal(getPasswordFeedback('MapleRiver9@').ready, true);
  assert.equal(getPasswordFeedback('Copper!Meadow#82').ready, true);
});

test('counts unicode bytes and rejects unsafe whitespace', () => {
  assert.equal(getPasswordFeedback('GoodPass1!' + 'ق'.repeat(35)).ready, false);
  assert.equal(getPasswordFeedback('GoodPass1!' + 'ق'.repeat(20)).ready, true);
  assert.equal(getPasswordFeedback(' GoodPassword123!').ready, false);
  assert.equal(getPasswordFeedback('').ready, false);
});
