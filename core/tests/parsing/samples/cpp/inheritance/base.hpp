#pragma once

namespace app {

class Base {
public:
    virtual ~Base() = default;
    virtual void run() = 0;
    virtual int score() const { return 0; }
};

}  // namespace app
