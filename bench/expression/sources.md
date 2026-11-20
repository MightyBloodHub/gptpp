# Historical tasks in the expression study

These three fixtures draw on changes in Redis, FastLED and Go. Each preserves a behavior shared by two identifiable upstream use sites and exposes one existing expression for repair in three languages. The projects, target changes and caller cases were selected before viewing any scored replies. The fixture definitions contain the expected answers and belong to the scorer. [Task definitions](tasks.py) · [Study protocol](protocol.md)

## Redis last-access timestamp

Redis records a 24-bit clock value on an object. At the parent revision, restoring an idle duration that crossed zero put the access timestamp roughly halfway around the clock, independent of the actual duration. The fix adds the clock maximum to the signed result of subtracting elapsed ticks. Redis's corresponding idle-time decoder uses the same maximum, 16,777,215. This detail matters for a timestamp just one tick before zero. [Before](https://github.com/redis/redis/blob/3db0f1a284e4fba703419b892b2d5b8d385afc06/src/object.c#L1199-L1213) · [Fix](https://github.com/redis/redis/commit/b458b2999b749950c5ea9468cfa5ab74782848c3) · [Clock constants](https://github.com/redis/redis/blob/b458b2999b749950c5ea9468cfa5ab74782848c3/src/server.h#L711-L713) · [Idle-time decoder](https://github.com/redis/redis/blob/b458b2999b749950c5ea9468cfa5ab74782848cfa5ab74782848c3/src/evict.c#L89-L99)

The RDB loader passes seconds with a multiplier of 1,000. The module API passes milliseconds with a multiplier of one. Both fixtures expose the timestamp written to the object. Inputs assume an existing object, LRU mode, a valid nonnegative idle duration and at most 10,000 elapsed ticks. The test oracle walks the clock back one tick at a time. Cases cover underflow, exact zero, retained timestamps and subsecond rounding. [RDB load call](https://github.com/redis/redis/blob/b458b2999b749950c5ea9468cfa5ab74782848c3/src/rdb.c#L2572-L2579) · [Module API call](https://github.com/redis/redis/blob/b458b2999b749950c5ea9468cfa5ab74782848c3/src/module.c#L8961-L8970)

## FastLED fractional byte scaling

FastLED added a compile-time option to make the top scale value retain the entire channel level. The portable C implementation multiplies the level by one more than the scale in fixed mode. The old mode still divides the original product by 256. The extract turns the configuration switch into a Boolean parameter and uses nonnegative integer division for the eight-bit right shift. [Before](https://github.com/FastLED/FastLED/blob/5b93491f66da32c118f177619375f582c938f128/lib8tion/scale8.h#L18-L30) · [Fix](https://github.com/FastLED/FastLED/commit/fee800a12e0ccde471379e8e4bd613d13fe1526b) · [Portable C implementation](https://github.com/FastLED/FastLED/blob/fee800a12e0ccde471379e8e4bd613d13fe1526b/lib8tion/scale8.h#L20-L30)

`lerp8by8` applies scaling to the absolute distance between its endpoints before adding or subtracting it. `map8` scales its **input** by the width of the output range before adding the low endpoint. That argument order affects fixed-mode rounding. The extract covers byte inputs and ordered map ranges. Its oracle multiplies exact rational weights and truncates once. Caller cases include increasing, decreasing and equal interpolation endpoints, zero-width ranges and both scaling modes. [Interpolation caller](https://github.com/FastLED/FastLED/blob/fee800a12e0ccde471379e8e4bd613d13fe1526b/lib8tion.h#L455-L469) · [Mapping caller](https://github.com/FastLED/FastLED/blob/fee800a12e0ccde471379e8e4bd613d13fe1526b/lib8tion.h#L555-L562)

## Go time-zone interval at the end of a leap year

Go's POSIX time-zone footer logic formerly ended the interval after the last transition at January 1 plus 365 days in every year. The fix extends the interval by one day in leap years. The extract measures seconds from January 1 and selects a northern-hemisphere rule with transitions at day offsets 70 and 310. It factors the last interval's duration into a day count multiplied by 86,400. The test oracle computes the year length by subtracting successive Gregorian January 1 dates. [Before](https://github.com/golang/go/blob/7f83fbe6a6d0b4f7bc29f0e88ec42562e47e0b6b/src/time/zoneinfo.go#L350-L364) · [Fix](https://github.com/golang/go/commit/4f25c33e83df34f27e939f40109c27831e508b09) · [Fixed interval calculation](https://github.com/golang/go/blob/4f25c33e83df34f27e939f40109c27831e508b09/src/time/zoneinfo.go#L337-L368)

Two public functions consume the interval through `Location.lookup`. `Time.ZoneBounds` exposes the end instant. `Date` uses the interval to decide whether applying an offset requires a second lookup. The second fixture observes that internal retry decision as zero or one. This measures a potentially unnecessary lookup, while the external date value may remain identical. Cases span leap centuries, non-leap centuries, ordinary years, both transitions, offsets of either sign and the final leap day. [Footer dispatch](https://github.com/golang/go/blob/4f25c33e83df34f27e939f40109c27831e508b09/src/time/zoneinfo.go#L201-L214) · [ZoneBounds caller](https://github.com/golang/go/blob/4f25c33e83df34f27e939f40109c27831e508b09/src/time/time.go#L1413-L1425) · [Date retry](https://github.com/golang/go/blob/4f25c33e83df34f27e939f40109c27831e508b09/src/time/time.go#L1754-L1769)

## Coverage

| Project | Public cases | Withheld target cases | Withheld caller 1 cases | Withheld caller 2 cases |
|---|---:|---:|---:|---:|
| Redis | 3 | 6 | 4 | 4 |
| FastLED | 3 | 6 | 4 | 4 |
| Go | 3 | 6 | 4 | 5 |

Each language runs all 52 cases. Every starter fails a public case and withheld cases in both callers. The three reference implementations per task must pass every case. The study measures repair of scalar extracts, with upstream I/O, configuration parsing and platform assembly outside the measured workload.

A separate translation audit compiled the pinned C and Go calculation blocks before and after each fix and compared their outputs with the corresponding Python fixtures. There were **zero mismatches in 288,140 comparisons**. Redis contributed 8,192 timestamp checks across both multipliers. FastLED contributed 270,336 checks, covering every pair of byte inputs in both modes and sampled calls to both upstream callers. Go contributed 9,612 interval ends across every year from 1600 through 2400 at six instants per year and revision. These comparisons check the fidelity of the fixtures. The model benchmark has three independent maintenance tasks.
