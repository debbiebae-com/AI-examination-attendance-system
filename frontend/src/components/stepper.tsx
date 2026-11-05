import { Check } from "lucide-react"
import { cn } from "@/lib/utils"

const steps = ["Details", "Photos", "Confirmation"]

export function Stepper({ current }: { current: number }) {
  return (
    <nav aria-label="Enrollment progress">
      <ol className="flex items-center gap-2 sm:gap-4">
        {steps.map((label, index) => {
          const done = index < current
          const active = index === current
          return (
            <li key={label} className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3" aria-current={active ? "step" : undefined}>
              <span
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-medium",
                  done && "border-primary bg-primary text-primary-foreground",
                  active && "border-primary bg-card text-primary",
                  !done && !active && "border-border bg-card text-muted-foreground",
                )}
              >
                {done ? <Check className="size-3.5" aria-hidden="true" /> : index + 1}
              </span>
              <span className={cn("truncate text-xs sm:text-sm", active ? "font-medium text-foreground" : "text-muted-foreground")}>
                {label}
              </span>
              {index < steps.length - 1 && <span className="ml-auto hidden h-px flex-1 bg-border sm:block" aria-hidden="true" />}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
