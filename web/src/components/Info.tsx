import { useState } from 'react'
import { Popover as PopoverPrimitive } from 'radix-ui'

/**
 * A one-sentence explanation, out of the way until asked for.
 *
 * Answers to both a hover (desktop) and a tap (phone, half the pool): hover
 * opens and closes with the pointer, a tap pins it open until the next tap
 * or an outside click/Escape closes it — Radix's own `onOpenChange` covers
 * that last part, so hover/pinned only need to agree on when to reset.
 */
export function Info({ text }: { text: string }) {
  const [hover, setHover] = useState(false)
  const [pinned, setPinned] = useState(false)
  const open = hover || pinned

  return (
    <PopoverPrimitive.Root
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setHover(false)
          setPinned(false)
        }
      }}
    >
      <PopoverPrimitive.Trigger asChild>
        <button
          type="button"
          aria-label={text}
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
          onClick={() => setPinned((p) => !p)}
          className="inline-flex size-3.5 shrink-0 cursor-help items-center justify-center rounded-full border border-current text-[9px] font-bold normal-case text-muted-foreground hover:text-foreground"
        >
          i
        </button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          side="top"
          sideOffset={6}
          className="z-50 max-w-64 rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md"
        >
          {text}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  )
}
