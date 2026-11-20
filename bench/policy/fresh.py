"""Fresh, locally authored policy maintenance fixtures for the v7 matched study.

The linked sources specify the rules. Each program, starter defect, pair of
consumers and set of expected results was written specifically for this corpus.
Expected values are hand-calculated independently of the reference functions.
"""
from bench.maintenance.cases_a import _callers, _function


def _params(spec):
    return [(s.lstrip('?'), 'bool' if s.startswith('?') else 'int') for s in spec.split()]


def _fn(name, spec, py, scalar):
    return _function(name, _params(spec), py, scalar)


def _task(case_id, form, target, spec, description, url, provenance, old, new, callers, public, heldout):
    names = [target, *[fn[0] for fn in callers]]
    def named(rows):
        return [(names[i], args, value) for i, args, value in rows]
    return dict(id=case_id, kind='maintenance', form=form, target=target, params=_params(spec),
                description=description, source_url=url, provenance=provenance,
                starter=_fn(target, spec, *old), reference=_fn(target, spec, *new),
                callers=_callers(*[_fn(*fn) for fn in callers]), public=named(public), heldout=named(heldout))


PAY = _task(
    'timesheet_overtime_premium', 'body', 'weekly_pay', 'hours rate ?eligible',
    'Payroll currently pays straight time for everyone. For eligible workers, pay the first 40 hours at rate '
    'and every additional hour at 1.5 times rate. Other workers keep straight time. Return total cents for '
    'one week. Hours are whole, 0..100. Rate is even, 800..5000 cents per hour. Weeks are independent.',
    'https://www.dol.gov/agencies/whd/fact-sheets/23-flsa-overtime-pay',
    'Local timesheet fixture using the federal FLSA overtime minimum for covered nonexempt workers. '
    'The eligible flag is established upstream. The fixture uses a single hourly rate and no other remuneration.',
    ('return hours * rate', 'return hours * rate;'),
    ('''if eligible and hours > 40:
    return hours * rate + (hours - 40) * (rate // 2)
return hours * rate''', '''if eligible && hours > 40 { return hours * rate + (hours - 40) * (rate / 2); }
return hours * rate;'''),
    [('fortnight_pay', 'first second rate ?eligible',
      'return weekly_pay(first, rate, eligible) + weekly_pay(second, rate, eligible)',
      'return weekly_pay(first, rate, eligible) + weekly_pay(second, rate, eligible);'),
     ('unpaid_balance', 'paid hours rate ?eligible',
      'return max(0, weekly_pay(hours, rate, eligible) - paid)',
      'let due = weekly_pay(hours, rate, eligible) - paid;\nreturn if due > 0 { due } else { 0 };')],
    [(1, (20, 50, 1000, True), 75000), (0, (41, 1200, True), 49800),
     (2, (42000, 41, 1000, False), 0)],
    [(0, (0, 800, True), 0), (0, (40, 1250, True), 50000), (0, (42, 802, True), 34486),
     (0, (100, 800, False), 80000), (0, (100, 5000, True), 650000),
     (1, (40, 41, 800, True), 65200), (1, (39, 39, 900, True), 70200),
     (1, (50, 50, 1200, False), 120000), (1, (45, 45, 1000, True), 95000),
     (2, (40100, 41, 1000, True), 1400), (2, (43000, 41, 1000, True), 0),
     (2, (10000, 20, 800, True), 6000), (2, (80000, 70, 1200, False), 4000)])


RAIL = _task(
    'rail_delay_claim', 'body', 'delay_credit', 'minutes fare ?refunded',
    'Update the claim calculator to award half the ticket fare for delays of at least 120 minutes. '
    'Keep the quarter fare for delays of 60..119 minutes, zero for shorter delays and zero whenever the '
    'ticket was refunded. Minutes are 0..600 and fare is a positive multiple of four cents. All other '
    'eligibility checks have passed.',
    'https://eur-lex.europa.eu/eli/reg/2021/782/oj/eng',
    'Local rail claims fixture for the minimum percentages in Regulation (EU) 2021/782 Article 19(1). '
    'Models a single, one-way fare, no minimum payout threshold, exemptions, or extraordinary circumstances.',
    ('return fare // 4 if minutes >= 60 and not refunded else 0',
     'return if minutes >= 60 && !refunded { fare / 4 } else { 0 };'),
    ('''if refunded or minutes < 60:
    return 0
return fare // 2 if minutes >= 120 else fare // 4''',
     '''if refunded || minutes < 60 { return 0; }
return if minutes >= 120 { fare / 2 } else { fare / 4 };'''),
    [('party_credit', 'tickets minutes fare ?refunded',
      'return tickets * delay_credit(minutes, fare, refunded)',
      'return tickets * delay_credit(minutes, fare, refunded);'),
     ('outstanding_claim', 'issued minutes fare ?refunded',
      'return max(0, delay_credit(minutes, fare, refunded) - issued)',
      'let left = delay_credit(minutes, fare, refunded) - issued;\nreturn if left > 0 { left } else { 0 };')],
    [(1, (3, 120, 2400, False), 3600), (0, (119, 2400, False), 600),
     (2, (100, 180, 2400, True), 0)],
    [(0, (59, 1000, False), 0), (0, (60, 1000, False), 250), (0, (121, 1004, False), 502),
     (0, (120, 400, True), 0), (0, (600, 4, False), 2),
     (1, (2, 130, 1200, False), 1200), (1, (4, 60, 1004, False), 1004),
     (1, (5, 240, 800, True), 0), (1, (1, 0, 3000, False), 0),
     (2, (100, 120, 404, False), 102), (2, (1000, 121, 1200, False), 0),
     (2, (5, 61, 2000, False), 495), (2, (0, 150, 1200, True), 0)])


SEMVER = _task(
    'release_candidate_order', 'body', 'compare_build', 'patch_a rc_a patch_b rc_b',
    'Compare versions with a common major and minor. Return -1, 0, or 1 according as A precedes, equals, '
    'or follows B. Compare patch numbers first. For equal patches a stable release (rc=-1) follows every '
    'rc.N. Two rc.N releases compare by numeric N. Patch and N are 0..999; ignore build metadata.',
    'https://semver.org/spec/v2.0.0.html',
    'Local release selector implements the subset of Semantic Versioning 2.0.0 rule 11 with equal major/minor '
    'and either no prerelease tag or a single rc.N suffix; the -1 representation is local.',
    ('''if patch_a < patch_b:
    return -1
return 1 if patch_a > patch_b else 0''',
     '''if patch_a < patch_b { return -1; }
return if patch_a > patch_b { 1 } else { 0 };'''),
    ('''if patch_a != patch_b:
    return 1 if patch_a > patch_b else -1
if rc_a == rc_b:
    return 0
if rc_a == -1 or (rc_b != -1 and rc_a > rc_b):
    return 1
return -1''', '''if patch_a != patch_b { return if patch_a > patch_b { 1 } else { -1 }; }
if rc_a == rc_b { return 0; }
if rc_a == -1 || (rc_b != -1 && rc_a > rc_b) { return 1; }
return -1;'''),
    [('offer_upgrade', 'installed rc_now offered rc_new',
      'return int(compare_build(offered, rc_new, installed, rc_now) > 0)',
      'return if compare_build(offered, rc_new, installed, rc_now) > 0 { 1 } else { 0 };'),
     ('below_floor', 'patch rc floor_patch floor_rc',
      'return int(compare_build(patch, rc, floor_patch, floor_rc) < 0)',
      'return if compare_build(patch, rc, floor_patch, floor_rc) < 0 { 1 } else { 0 };')],
    [(1, (5, 2, 5, -1), 1), (0, (4, -1, 5, 0), -1), (2, (8, 10, 8, 2), 0)],
    [(0, (0, -1, 0, -1), 0), (0, (4, 10, 4, 2), 1), (0, (4, 0, 4, -1), -1),
     (0, (8, 3, 8, 3), 0), (0, (9, 0, 8, -1), 1),
     (1, (6, 0, 6, 1), 1), (1, (6, -1, 6, 90), 0), (1, (6, -1, 7, 0), 1),
     (1, (6, 3, 5, -1), 0), (2, (5, 2, 5, 3), 1), (2, (5, -1, 5, 999), 0),
     (2, (4, -1, 5, 0), 1), (2, (4, 8, 4, 8), 0)])


CRON = _task(
    'cron_restricted_days', 'body', 'day_selected', 'wanted_day wanted_weekday day weekday',
    'The schedule parser encodes a wildcard as -1. Day of month ranges 1..31 and weekday 0..6. With both '
    'selectors restricted, a match on either one should trigger the job. With just one selector restricted, '
    'that one must match. Two wildcards match any date. Return 1 for a match, 0 otherwise. Month, hour '
    'and minute are checked outside this function.',
    'https://man.openbsd.org/crontab.5',
    'Local batch scheduler follows the day-field behavior in the OpenBSD crontab manual. Selectors are '
    'single numeric literals or a plain wildcard; ranges, lists and steps are outside the fixture.',
    ('return int((wanted_day == -1 or wanted_day == day) and (wanted_weekday == -1 or wanted_weekday == weekday))',
     'return if (wanted_day == -1 || wanted_day == day) && (wanted_weekday == -1 || wanted_weekday == weekday) { 1 } else { 0 };'),
    ('''if wanted_day == -1 and wanted_weekday == -1:
    return 1
return int(wanted_day == day or wanted_weekday == weekday)''',
     '''if wanted_day == -1 && wanted_weekday == -1 { return 1; }
return if wanted_day == day || wanted_weekday == weekday { 1 } else { 0 };'''),
    [('jobs_to_enqueue', 'copies ?time_ok wanted_day wanted_weekday day weekday',
      'return copies * day_selected(wanted_day, wanted_weekday, day, weekday) if time_ok else 0',
      'return if time_ok { copies * day_selected(wanted_day, wanted_weekday, day, weekday) } else { 0 };'),
     ('two_day_runs', 'wanted_day wanted_weekday first_day first_weekday second_day second_weekday',
      'return day_selected(wanted_day, wanted_weekday, first_day, first_weekday) + day_selected(wanted_day, wanted_weekday, second_day, second_weekday)',
      'return day_selected(wanted_day, wanted_weekday, first_day, first_weekday) + day_selected(wanted_day, wanted_weekday, second_day, second_weekday);')],
    [(1, (4, True, 7, 3, 7, 6), 4), (0, (-1, 3, 7, 6), 0),
     (2, (-1, -1, 5, 5, 6, 6), 2)],
    [(0, (21, 0, 20, 0), 1), (0, (21, 0, 21, 0), 1), (0, (21, 0, 20, 1), 0),
     (0, (31, -1, 30, 0), 0), (0, (-1, -1, 1, 0), 1),
     (1, (5, True, 13, 5, 12, 5), 5), (1, (5, False, 13, 5, 12, 5), 0),
     (1, (2, True, -1, 0, 14, 0), 2), (1, (10, True, 28, -1, 27, 1), 0),
     (2, (23, 1, 23, 0, 24, 1), 2), (2, (10, 3, 9, 2, 10, 3), 1),
     (2, (-1, 6, 9, 6, 10, 0), 1), (2, (31, -1, 5, 1, 6, 2), 0)])


PERMS = _task(
    'permission_class_precedence', 'body', 'selected_mask', '?owner ?in_group owner_mask group_mask other_mask',
    'The file browser gives the group permissions to owners who also belong to the group. Select exactly '
    'one three-bit mask: an owner uses owner_mask, another group member uses group_mask, everyone else '
    'uses other_mask. A zero mask still decides the result. Inputs are standard read/write/execute masks '
    'in 0..7. Callers use the mask for previews and launcher availability.',
    'https://sourceware.org/glibc/manual/2.41/html_node/Access-Permission.html',
    'Local file browser reproduces the Unix owner/group/other class selection in the GNU C Library manual. '
    'Only ordinary unprivileged users and mode bits are modeled. There are no ACLs or privilege overrides.',
    ('''if in_group:
    return group_mask
return owner_mask if owner else other_mask''',
     '''if in_group { return group_mask; }
return if owner { owner_mask } else { other_mask };'''),
    ('''if owner:
    return owner_mask
return group_mask if in_group else other_mask''',
     '''if owner { return owner_mask; }
return if in_group { group_mask } else { other_mask };'''),
    [('preview_bytes', 'length ?owner ?in_group owner_mask group_mask other_mask',
      'return length if selected_mask(owner, in_group, owner_mask, group_mask, other_mask) >= 4 else 0',
      'return if selected_mask(owner, in_group, owner_mask, group_mask, other_mask) >= 4 { length } else { 0 };'),
     ('launcher_visible', '?owner ?in_group owner_mask group_mask other_mask',
      'return selected_mask(owner, in_group, owner_mask, group_mask, other_mask) % 2',
      'return selected_mask(owner, in_group, owner_mask, group_mask, other_mask) % 2;')],
    [(1, (80, True, True, 0, 7, 7), 0), (0, (False, True, 7, 2, 5), 2),
     (2, (False, False, 0, 0, 1), 1)],
    [(0, (True, True, 2, 7, 0), 2), (0, (True, True, 5, 0, 0), 5),
     (0, (True, False, 3, 5, 6), 3), (0, (False, True, 7, 0, 7), 0),
     (0, (False, False, 1, 3, 4), 4), (1, (32, True, True, 4, 1, 0), 32),
     (1, (12, False, True, 7, 3, 7), 0), (1, (1, False, False, 2, 4, 6), 1),
     (1, (15, True, False, 0, 7, 5), 0), (2, (True, True, 6, 7, 7), 0),
     (2, (True, True, 1, 2, 6), 1), (2, (False, True, 0, 5, 0), 1),
     (2, (False, False, 1, 5, 2), 0)])


UNIQUE = _task(
    'nullable_unique_key', 'expr', 'key_conflict', 'tenant_a code_a tenant_b code_b ?nulls_equal',
    'Support a UNIQUE NULLS NOT DISTINCT option for the pair (tenant, code). A conflict requires the '
    'same tenant. Two equal non-null codes conflict in either mode. Two null codes conflict only with '
    'nulls_equal enabled. One null and one non-null never conflict. Return 1 for conflict, else 0. '
    'Tenants and real codes are 0..1000. Code -1 represents null.',
    'https://www.postgresql.org/docs/15/ddl-constraints.html',
    'Local preflight of a two-column unique constraint in PostgreSQL 15, section 5.4.3. The tenant is '
    'never null. The fixture checks a bounded snapshot, independent of database locking or transaction state.',
    ('return int(tenant_a == tenant_b and code_a >= 0 and code_a == code_b)',
     'return if tenant_a == tenant_b && code_a >= 0 && code_a == code_b { 1 } else { 0 };'),
    ('return int(tenant_a == tenant_b and code_a == code_b and (code_a >= 0 or nulls_equal))',
     'return if tenant_a == tenant_b && code_a == code_b && (code_a >= 0 || nulls_equal) { 1 } else { 0 };'),
    [('insert_allowed', 'tenant code existing_tenant existing_code ?nulls_equal',
      'return 1 - key_conflict(tenant, code, existing_tenant, existing_code, nulls_equal)',
      'return 1 - key_conflict(tenant, code, existing_tenant, existing_code, nulls_equal);'),
     ('tenant_conflicts', 'tenant incoming first second ?nulls_equal',
      'return key_conflict(tenant, incoming, tenant, first, nulls_equal) + key_conflict(tenant, incoming, tenant, second, nulls_equal)',
      'return key_conflict(tenant, incoming, tenant, first, nulls_equal) + key_conflict(tenant, incoming, tenant, second, nulls_equal);')],
    [(1, (4, -1, 4, -1, True), 0), (0, (0, -1, 0, -1, False), 0),
     (2, (2, 5, -1, 5, True), 1)],
    [(0, (12, -1, 12, -1, True), 1), (0, (12, -1, 13, -1, True), 0),
     (0, (0, 0, 0, 0, False), 1), (0, (9, -1, 9, 0, True), 0), (0, (9, 1, 8, 1, False), 0),
     (1, (1, -1, 1, -1, True), 0), (1, (1, -1, 1, -1, False), 1),
     (1, (8, 0, 8, -1, True), 1), (1, (8, 1, 8, 1, True), 0),
     (2, (7, -1, -1, -1, True), 2), (2, (7, -1, 5, -1, True), 1),
     (2, (9, -1, -1, -1, False), 0), (2, (3, 4, 4, 4, False), 2)])


BOWL = _task(
    'tenpin_final_rack', 'body', 'rack_pins', 'frame balls first second',
    'The lane controller handles ordinary frames; add the tenth. Return the number of pins standing for '
    'the next delivery in this frame, or 0 if it has ended. A new frame starts with 10. In frames 1..9, '
    'a strike ends the frame; otherwise the second ball faces the pins left. In frame 10, a first-ball '
    'strike starts the second ball with 10. A third ball is earned for a first-ball strike or a two-ball '
    'spare. After a strike then a nonstrike, the third ball faces 10 minus the second pinfall; after two '
    'strikes or a spare it faces 10. Three balls end the frame. Inputs describe valid states, balls=0..3, '
    'first and second are pinfalls of completed balls (0 for an unplayed ball).',
    'https://bowling.sport/universal-playing-rules-chapter-2/',
    'Local rack-display and lane dispatch fixture based on International Bowling Federation tenpin rules '
    '2.1.1–2.1.8. Only credited, legal deliveries are modeled; no fouls, missing pins or provisional balls.',
    ('''if balls == 0:
    return 10
return 10 - first if balls == 1 else 0''',
     '''if balls == 0 { return 10; }
return if balls == 1 { 10 - first } else { 0 };'''),
    ('''if balls == 0:
    return 10
if balls == 1:
    return 10 if frame == 10 and first == 10 else 10 - first
if frame == 10 and balls == 2:
    if first == 10:
        return 10 if second == 10 else 10 - second
    if first + second == 10:
        return 10
return 0''',
     '''if balls == 0 { return 10; }
if balls == 1 { return if frame == 10 && first == 10 { 10 } else { 10 - first }; }
if frame == 10 && balls == 2 {
    if first == 10 { return if second == 10 { 10 } else { 10 - second }; }
    if first + second == 10 { return 10; }
}
return 0;'''),
    [('roll_requested', 'frame balls first second',
      'return int(rack_pins(frame, balls, first, second) > 0)',
      'return if rack_pins(frame, balls, first, second) > 0 { 1 } else { 0 };'),
     ('pair_display', 'frame balls_a first_a second_a balls_b first_b second_b',
      'return rack_pins(frame, balls_a, first_a, second_a) + rack_pins(frame, balls_b, first_b, second_b)',
      'return rack_pins(frame, balls_a, first_a, second_a) + rack_pins(frame, balls_b, first_b, second_b);')],
    [(1, (10, 2, 4, 6), 1), (0, (10, 2, 10, 3), 7), (2, (9, 1, 5, 0, 1, 10, 0), 5)],
    [(0, (10, 1, 10, 0), 10), (0, (10, 2, 10, 10), 10), (0, (10, 2, 10, 0), 10),
     (0, (10, 2, 3, 6), 0), (0, (10, 3, 10, 4), 0), (0, (5, 1, 10, 0), 0),
     (1, (10, 2, 10, 9), 1), (1, (1, 0, 0, 0), 1), (1, (9, 2, 7, 3), 0),
     (1, (10, 3, 2, 8), 0), (2, (10, 2, 0, 10, 2, 10, 6), 14),
     (2, (10, 3, 10, 10, 0, 0, 0), 10), (2, (7, 1, 4, 0, 1, 2, 0), 14)])


MIDI = _task(
    'midi_zero_velocity_release', 'body', 'note_action', 'status velocity',
    'Classify a MIDI channel-voice message for the synth. A Note On (status 144..159) with positive '
    'velocity starts a note (+1), but with zero velocity it releases a note (-1). An explicit Note Off '
    '(128..143) always releases (-1). Other status bytes (160..239) return 0, including at zero velocity. '
    'Velocity is 0..127. Ignore the channel number within each status range.',
    'https://www.w3.org/TR/2015/WD-webmidi-20150317/#a-simple-monophonic-sine-wave-midi-synthesizer',
    'Local MIDI event classifier follows the W3C Web MIDI API draft synthesizer example, which dispatches '
    'zero-velocity Note On as Note Off. A per-key gate and release counter are local consumer interfaces.',
    ('''if status < 144:
    return -1
return 1 if status < 160 else 0''',
     '''if status < 144 { return -1; }
return if status < 160 { 1 } else { 0 };'''),
    ('''if status < 144:
    return -1
if status < 160:
    return 1 if velocity > 0 else -1
return 0''',
     '''if status < 144 { return -1; }
if status < 160 { return if velocity > 0 { 1 } else { -1 }; }
return 0;'''),
    [('key_gate', '?was_down status velocity',
      '''action = note_action(status, velocity)
if action == 0:
    return int(was_down)
return int(action > 0)''',
      '''let action = note_action(status, velocity);
if action == 0 { return if was_down { 1 } else { 0 }; }
return if action > 0 { 1 } else { 0 };'''),
     ('release_count', 'a va b vb',
      'return int(note_action(a, va) < 0) + int(note_action(b, vb) < 0)',
      '''let first = if note_action(a, va) < 0 { 1 } else { 0 };
return first + if note_action(b, vb) < 0 { 1 } else { 0 };''')],
    [(1, (True, 144, 0), 0), (0, (143, 37), -1), (2, (160, 0, 159, 127), 0)],
    [(0, (159, 0), -1), (0, (144, 1), 1), (0, (128, 0), -1), (0, (160, 0), 0),
     (0, (239, 100), 0), (1, (False, 155, 0), 0), (1, (False, 159, 1), 1),
     (1, (True, 161, 0), 1), (1, (True, 139, 64), 0), (2, (149, 0, 150, 0), 2),
     (2, (143, 127, 159, 0), 2), (2, (144, 10, 128, 0), 1), (2, (239, 0, 160, 127), 0)])


# Hand-selected to exercise scalar policies in distinct domains, including arithmetic,
# eligibility, precedence and multi-stage decisions. This is not a production sample.
TASKS = [PAY, RAIL, SEMVER, CRON, PERMS, UNIQUE, BOWL, MIDI]
