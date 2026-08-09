import { Link } from 'react-router-dom'
import { BANDS, BREAK_EVEN, HOMER_TEAMS, TEAM_2025 } from '@/lib/consensus'

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
          <Link to="/view" className="text-primary underline-offset-4 hover:underline">
            Team
          </Link>{' '}
          page is where the meeting builds it.
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
            <b className="text-foreground">Line size</b> — the big one.{' '}
            {BANDS.map((b) => `${b.label} hit ${b.pct}%`).join(', ')} across{' '}
            {BANDS.reduce((n, b) => n + b.n, 0)} graded picks. We handle close games and we do not
            handle big numbers.
          </li>
          <li>
            <b className="text-foreground">Split or agreed</b> — agreement counts{' '}
            <i>against</i> a side. The games we all agreed on went 45.2%; the ones we argued about
            went 52.4%.
          </li>
          <li>
            <b className="text-foreground">Best-bet slot</b> — our best bets hit 41.4%. Naming a
            pick our most confident has been an anti-signal.
          </li>
          <li>
            <b className="text-foreground">Home or road</b> — home picks 45.2%, road 50.1%.
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
          All of it comes from one season, 777 graded picks. Only the line-size split clears
          statistical significance; everything else is directional. Full working in{' '}
          <code>notes/team-page-consensus-analysis.md</code>.
        </p>
      </Section>
    </div>
  )
}
