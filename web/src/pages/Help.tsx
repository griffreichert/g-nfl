import { Link } from 'react-router-dom'
import { BREAK_EVEN, HOMER_TEAMS, TEAM_2025 } from '@/lib/consensus'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <h2 className="mb-2 text-base font-bold">{title}</h2>
      <div className="flex flex-col gap-2 text-sm text-muted-foreground">{children}</div>
    </section>
  )
}

/** A tappable state and what it does, so the cycle isn't something you discover. */
function Step({ n, children }: { n: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-2">
      <span className="tabular shrink-0 font-semibold text-foreground">{n}</span>
      <span>{children}</span>
    </li>
  )
}

export default function Help() {
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <h1 className="text-xl font-bold sm:text-2xl">How this works</h1>

      <Section title="The week">
        <p>
          Everyone submits their own picks on the{' '}
          <Link to="/picks" className="text-primary underline-offset-4 hover:underline">
            Picks
          </Link>{' '}
          page during the week. Then we get together and agree the one set of picks Reichert
          submits to the pool — that entry is called <b className="text-foreground">TEAM</b>, and
          the{' '}
          <Link to="/picks" className="text-primary underline-offset-4 hover:underline">
            Make Picks
          </Link>{' '}
          page is where the meeting builds it.
        </p>
        <p>
          Sign in with your name and a PIN. Your picks are saved against whoever is signed
          in, so the record of who said what is worth keeping.
        </p>
      </Section>

      <Section title="What the site is for">
        <p>
          It is a veto machine and a ledger. Over six seasons nobody in this pool has shown
          skill: the pool as a whole went 50.12% and its best entry sits exactly where chance
          puts the best of sixteen. Two entries are past the noise threshold on the losing
          side and one of them is us.
        </p>
        <p>
          So the site does not try to find winners. It flags the sides we lose on, and it
          keeps score against the entries we could have submitted instead. Getting from{' '}
          {TEAM_2025.rate}% to the pool's own 50% is worth more than any edge anyone here has
          demonstrated, and it needs no skill at all.
        </p>
        <p>
          Run <code>make case</code> for the full argument with every number in it, generated
          from the same code that runs this site.
        </p>
      </Section>

      <Section title="The guardrails">
        <p>
          A red flag on a side means our own record says we lose on that kind of pick, over
          five seasons and in most of them individually. The rules and their rates are fitted
          from the record and served to this page, so nothing here can quietly go stale.
        </p>
        <p>
          They only ever say <i>not this side</i>. Out of sample the rating reliably finds bad
          picks and cannot rank good ones, so it never tells you what to take. You can
          override any of them on the TEAM entry; you just have to say why in the note, so the
          override is on the record.
        </p>
      </Section>

      <Section title="The ledger">
        <p>
          The{' '}
          <Link to="/performance" className="text-primary underline-offset-4 hover:underline">
            Performance
          </Link>{' '}
          page scores TEAM every week against the entries it could have been: the majority of us,
          whoever was leading going into that week, the mechanical{' '}
          <b className="text-foreground">No Homers</b> entry, and the two models.
        </p>
        <p>
          This exists because two separate sources say the meeting costs us about 1.5 points
          of hit rate against our own members. If TEAM keeps losing to the majority, that is
          the finding, and we change how we do this in October rather than in April.
        </p>
      </Section>

      <Section title="What one entry contains">
        <ul className="flex flex-col gap-1">
          <li>
            <b className="text-foreground">Best bet</b> — 1 pick, worth 2 points.
          </li>
          <li>
            <b className="text-foreground">Regulars</b> — 5 picks, 1 point each.
          </li>
          <li>
            <b className="text-foreground">MNF</b> — 1 pick on the Monday night game, 1 point.
          </li>
          <li>
            <b className="text-foreground">Underdog</b> — 1 dog. If it wins outright we score
            points equal to its spread. Nothing if it loses, even by a point.
          </li>
          <li>
            <b className="text-foreground">Survivor</b> — 1 team, no reuse all season, out after
            the second loss.
          </li>
        </ul>
        <p>
          The best bet, the five regulars and MNF must all be on{' '}
          <b className="text-foreground">different games</b>. A push pays half: 1 point on a best
          bet, half a point on a regular or MNF. All of it grades against the{' '}
          <b className="text-foreground">pool spread</b> — the Friday line the pool posts — not the
          market line.
        </p>
      </Section>

      <Section title="Building the entry on the Team page">
        <p>Tap a side of any game. Each tap moves that side to the next state:</p>
        <ol className="flex flex-col gap-1">
          <Step n="1.">
            first tap — the side becomes a <b className="text-foreground">Regular</b>
          </Step>
          <Step n="2.">
            second tap — it becomes the <b className="text-foreground">Best bet</b>. If another
            game was holding the best bet, that one steps down to a regular rather than being
            thrown out
          </Step>
          <Step n="3.">third tap — it comes off the entry</Step>
        </ol>
        <p>
          Tapping the <i>other</i> side of a game you have already used switches sides and keeps
          whatever slot that game held — a best bet stays a best bet. The Monday game only ever
          holds MNF, so there it is one tap on, one tap off.
        </p>
        <p>
          Once all seven slots are full the games you haven't used go dim — take something off
          first to free a slot. Games already in the entry stay live so you can keep switching
          sides. The counter at the top of the page tells you what is still open, and{' '}
          <b className="text-foreground">Submit as TEAM</b> saves the whole entry.
        </p>
        <p>
          <b className="text-foreground">Underdog</b> and{' '}
          <b className="text-foreground">Survivor</b> have their own rows below the games — tap a
          team to pick it, tap it again to clear. Survivor greys out every team we have already
          spent this season, so you cannot burn one twice. Neither carries a rating: they are
          separate pools with different objectives, and the model behind the rating does not
          describe either of them.
        </p>
      </Section>

      <Section title="The 0-10 rating">
        <p>
          Every side carries a rating. <b className="text-foreground">5.0 is break-even</b> — the{' '}
          {BREAK_EVEN}% you need to hit at -110 just to stay level. Above 5 a side is
          worth a slot, below 5 it costs us money over time. Best first, so the top of the board is
          where the entry should come from.
        </p>
        <p>
          It is deliberately <i>not</i> a percentage. The numbers underneath it are hit rates from a
          single season, and a rate printed to a decimal reads like a win probability it has not
          earned.
        </p>
        <p>Hover or tap a rating to see exactly what built it. The terms are:</p>
        <ul className="flex flex-col gap-1">
          <li>
            <b className="text-foreground">The guardrails</b> — the one measured term. Each is a
            cut of our own record that hit below the field's own rate, and hit below it in most
            seasons. They are served by the API and refitted from six seasons of picks on every
            deploy, so this page can no longer tell you a number the record has moved on from.
            They only ever say <i>not this side</i>: out of sample the rating reliably finds bad
            picks and cannot rank the good ones.
          </li>
          <li>
            <b className="text-foreground">What used to be here</b> — split-or-agreed, the
            best-bet slot, and home-or-road on its own were all terms in this rating until the
            record was recomputed per game rather than per pick. The room puts three votes on the
            average game, so a per-pick rate counts one game three times and makes every split
            look sharper than it is. Shrunk for sample size, those three sat on the field's base
            rate exactly. They were removed rather than shrunk, because a term worth zero should
            not be shown as if it were worth something.
          </li>
          <li>
            <b className="text-foreground">Homer</b> and{' '}
            <b className="text-foreground">stuck on them</b> — someone backing their own club (
            {Object.keys(HOMER_TEAMS).join(', ')}), or a team they have already taken four or more
            times this season. These two are <b className="text-foreground">judgement, not
            measured</b> — nothing in the data grades them, so they are capped and can only ever
            break a tie. They are marked as judgement in the breakdown.
          </li>
        </ul>
      </Section>

      <Section title="The pills, and why some have two names">
        <p>
          The pills on each side are who picked it. A star means they made it their best bet.
        </p>
        <p>
          Two names in one pill means those two pick the same side over 90% of the time, so we
          count them once. Ben submits bModel verbatim — a "5-2" containing both is really 4-2, and
          the room reads it as stronger than it is.
        </p>
      </Section>

      <Section title="Why the page argues with you">
        <p>
          In 2025 TEAM took {TEAM_2025.rate}% of the available pool points — last, behind every
          individual member — while following the majority on {TEAM_2025.rubberStamp} games. The
          best of us ({TEAM_2025.best}) took {TEAM_2025.bestRate}%.
        </p>
        <p>
          Averaging the room is what loses. The entry the board proposes is a starting point to
          argue with, not a vote to ratify.
        </p>
        <p className="text-xs">
          That part still holds — it is about how an averaged entry gets built, not about which
          games cover. What does not hold is anything that used a per-pick rate: one season is 225
          distinct games, and only line size crossed with venue survives being counted properly
          and shrunk for sample size. Everything else is directional at best. Full working in{' '}
          <code>notes/pick-analytics.md</code>.
        </p>
      </Section>
    </div>
  )
}
