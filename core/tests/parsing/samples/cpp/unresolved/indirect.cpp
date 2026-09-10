#include <functional>

namespace app {

struct Job {
    int step;
};

void dispatch(int value, void (*fn)(int)) {
    fn(value);
}

int call_lambda() {
    auto twice = [](int value) { return value * 2; };
    return twice(21);
}

int call_member_pointer(Job &job, int (Job::*pmf)()) {
    return (job.*pmf)();
}

int call_std_function(std::function<int(int)> handler) {
    return handler(1);
}

int call_casted_pointer(void *raw) {
    return ((int (*)(void *))raw)(raw);
}

}  // namespace app
