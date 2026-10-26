import * as React from "react"
import useEmblaCarousel from "embla-carousel-react"

import { cn } from "../../lib/utils"

/**
 * Carousel primitive (shadcn/ui style) backed by `embla-carousel-react`.
 *
 * Dependencies: `embla-carousel-react` — the carousel API (scroll, slide
 * alignment, keyboard navigation and prev/next control) is delegated to it
 * so this component stays small and dependency-free otherwise.
 *
 * Usage:
 *   const [selected, setSelected] = useState(0)
 *   <Carousel>
 *     <CarouselContent>
 *       <CarouselItem>...</CarouselItem>
 *     </CarouselContent>
 *     <CarouselPrevious onClick={scrollPrev}>‹</CarouselPrevious>
 *     <CarouselNext onClick={scrollNext}>›</CarouselNext>
 *   </Carousel>
 *
 * The parent owns `selected` and calls `scrollPrev`/`scrollNext`/`canScrollPrev`/
 * `canScrollNext` from the hook returned by `useCarousel`.
 */

export function useCarousel() {
  const [emblaApi, setEmblaApi] = React.useState(null)

  // useEmblaCarousel returns [setViewport, api]
  const [setViewport, api] = useEmblaCarousel(
    {
      loop: false,
      draggable: true,
      // Arrow-key navigation is handled by embla when focus is inside the
      // carousel container; the parent must keep focus within it.
    },
    []
  )

  React.useEffect(() => {
    if (api) setEmblaApi(api)
  }, [api])

  const emblaRef = setViewport

  const canScrollPrev = React.useCallback(() => {
    if (!emblaApi) return false
    return emblaApi.canScrollPrev()
  }, [emblaApi])

  const canScrollNext = React.useCallback(() => {
    if (!emblaApi) return false
    return emblaApi.canScrollNext()
  }, [emblaApi])

  const scrollPrev = React.useCallback(() => {
    if (!emblaApi) return
    emblaApi.scrollPrev()
  }, [emblaApi])

  const scrollNext = React.useCallback(() => {
    if (!emblaApi) return
    emblaApi.scrollNext()
  }, [emblaApi])

  const scrollTo = React.useCallback(
    (index) => {
      if (!emblaApi) return
      emblaApi.scrollTo(index)
    },
    [emblaApi]
  )

  return {
    emblaRef,
    emblaNodeRef: setViewport,
    emblaNode: null,
    canScrollPrev,
    canScrollNext,
    scrollPrev,
    scrollNext,
    scrollTo,
  }
}

const Carousel = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("relative", className)}
    {...props}
  />
))
Carousel.displayName = "Carousel"

const CarouselContent = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("overflow-hidden", className)}
    {...props}
  />
))
CarouselContent.displayName = "CarouselContent"

const CarouselItem = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("min-w-0 shrink-0 grow-0", className)}
    {...props}
  />
))
CarouselItem.displayName = "CarouselItem"

const CarouselPrevious = React.forwardRef(({ className, ...props }, ref) => (
  <button
    ref={ref}
    type="button"
    className={cn(
      "absolute inset-y-0 left-0 flex items-center pl-4",
      className
    )}
    {...props}
  />
))
CarouselPrevious.displayName = "CarouselPrevious"

const CarouselNext = React.forwardRef(({ className, ...props }, ref) => (
  <button
    ref={ref}
    type="button"
    className={cn(
      "absolute inset-y-0 right-0 flex items-center pr-4",
      className
    )}
    {...props}
  />
))
CarouselNext.displayName = "CarouselNext"

export { Carousel, CarouselContent, CarouselItem, CarouselPrevious, CarouselNext }
