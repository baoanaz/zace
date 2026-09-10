#include "b.h"

static int helper(int value) { return value + 1; }

int helper2(int value) { return helper(value) * 2; }
