// Keep an arithmetic fault inside the FFI call on this thread.
#include <setjmp.h>
#include <stdint.h>
#include <stdlib.h>

static _Thread_local jmp_buf *gpp_boundary;
static _Thread_local int32_t gpp_fault_code;

_Noreturn void gpp_fault(int32_t code) {
    if (!gpp_boundary) abort();
    gpp_fault_code = code;
    longjmp(*gpp_boundary, 1);
}
