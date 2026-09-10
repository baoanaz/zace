#include "templates.hpp"

namespace use {

int use_templates(int a, int b) {
    return algo::max_value<int>(a, b);
}

int use_box() {
    algo::Box<int> box;
    box.set(1);
    return box.get();
}

}  // namespace use
