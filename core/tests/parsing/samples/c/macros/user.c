#include "macros.h"

void use_macros(int value) {
    int size = MAX_LEN;
    int squared = SQUARE(value);
    LOG("size=%d", size);
    (void)squared;
}
