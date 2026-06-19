interface PoweredByProps {
  className?: string;
}

export function PoweredBy({ className = "" }: PoweredByProps) {
  return (
    <div className={`flex items-center justify-center gap-1.5 text-[10.5px] font-sans text-white dark:text-muted-foreground/60 select-none ${className}`}>
      Powered by
      <strong className="font-bold text-foreground/80 dark:text-zinc-300 ">
        Fagoon
        <span className='text-red-600 px-1'>
          AI
        </span>
      </strong>
    </div>
  );
}
