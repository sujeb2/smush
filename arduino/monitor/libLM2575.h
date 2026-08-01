#ifndef libLM2575
#define libLM2575

class libLM2575 {
    int _in1;
    int _in2;
    int _pwm;
public:
    libLM2575(int in1, int in2, int pwm);
    void forward();
    void backward();
    void leftWheelForward();
    void leftWheelBackward();
    void rightWheelForward();
    void rightWheelBackward();
    int getLn1();
    int getLn2();
};

#endif