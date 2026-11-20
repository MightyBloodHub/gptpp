#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

extern int64_t gpp_entry(void);

_Noreturn void gpp_fault(int32_t category) {
    const char *name;
    switch (category) {
    case 1: name = "IntegerOverflow"; break;
    case 2: name = "DivisionByZero"; break;
    case 3: name = "InvalidBounds"; break;
    default: name = "InternalError"; break;
    }
    fprintf(stderr, "fault: %s\n", name);
    exit(1);
}

int main(void) {
    printf("%" PRId64 "\n", gpp_entry());
    return 0;
}
