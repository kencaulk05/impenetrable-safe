# Part 1: fitting the V

Fitting AnnaCode's V example (120 points, x from 20 to 100, y = 2|x - 60| plus noise of 2) by gradient descent: first one neuron with a ReLU, then a hidden layer of ReLU neurons.

## Run it

```
pip install numpy matplotlib openpyxl
python v_fit.py               # prints the five iterations, trains for 2000 epochs, writes the two plots in images/
python tests/test_v_fit.py    # checks that the Python and the spreadsheet give the same numbers
```

## The spreadsheet: v_fit.xlsx

One neuron with a ReLU, `output = max(0, m x + b)`, five iterations of gradient descent on m and b.

| Columns | What they are |
|---|---|
| A, B | the data: x and y |
| D to K | one row per iteration: m, b, de/dm, de/db, new m, new b, and the loss |
| M2 | the learning rate alpha (0.0001) |
| O to R | the neuron's output at the start and after iterations 1, 2 and 5 (used by the first chart) |

The math in each row, with e = y - output and r = 1 where m x + b > 0 (else 0), over the N = 120 points:

- de/dm = -(2/N) * sum of (e * r * x)
- de/db = -(2/N) * sum of (e * r)
- new m = m - alpha * de/dm,  new b = b - alpha * de/db
- loss = (1/N) * sum of e^2

It starts at m = 0.1, b = 0. The first chart shows the data and the neuron's output after each iteration; the second shows the loss, which falls from 1947 to 804.

## The Python: v_fit.py

- **Part 1** is the same neuron, data, start and learning rate as the spreadsheet. It prints the same five rows, then keeps going to 2000 epochs: the loss only reaches 783. One neuron with a ReLU is one straight line with a single bend at zero, so it cannot follow both arms of the V.
- **Part 2** is a hidden layer of 2 ReLU neurons and an output neuron that adds them up, `y_hat = v1 relu(w1 x + c1) + v2 relu(w2 x + c2) + d`. Each hidden neuron makes one hinge, and two hinges make the V. The forward pass, the backpropagation (one chain-rule step per line) and the gradient-descent step are written out in `train_layer`. The data is rescaled to mean 0 and spread 1 first, so one learning rate (0.05) suits every weight. After 2000 epochs the loss is 3.98: a typical miss of 2.00, the size of the noise.

| Plot | |
|---|---|
| `images/v_fit_data_and_fit.png` | the data, the one-neuron fit and the hidden-layer fit |
| `images/v_fit_loss.png` | the loss of both as a function of epoch |

The hidden layer starts from random weights (seed 2). Some starts end on one arm of the V instead: of seeds 0 to 7, three reach the noise level and five do not.
