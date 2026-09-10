#pragma once

namespace outer {
namespace inner {

class Widget {
public:
    Widget();
    ~Widget();
    void run();
    int compute(int value) const;

private:
    int value_;
};

}  // namespace inner
}  // namespace outer
