# Fitting Anna's V with gradient descent

Part 1 of the lock project: find the weights of a model by gradient descent, by hand, on the V example from AnnaCode: first one neuron, then a neuron with a ReLU, then a hidden layer of ReLU neurons. There is a NumPy version with every gradient written out, a PyTorch version that checks it, and a spreadsheet whose five iterations are live formulas.

**The data** is AnnaCode's "V" example, generated the way its code generates it (`network/training.py`): 120 random points, x uniform on 20 to 100, y = 2|x - 60| plus Gaussian noise of 2. AnnaCode draws new points every time; here they come from a fixed seed (0) so every number below can be reproduced. To fit other points, such as data saved from AnnaCode, put them in a CSV with columns `x,y` and add `--data file.csv` to the commands below.

## Run it

```
pip install numpy matplotlib openpyxl torch
python v_fit.py                       # the rescaling demo, the five-step table, the fits, the survey, the plots, the gradient check
python make_v_spreadsheet.py          # v_fit.xlsx (every iteration is a live formula)
python v_fit_torch.py                 # PyTorch's autograd against the hand-written gradients
python tests/test_v_fit.py            # 52 checks
```

## What it shows

| | |
|---|---|
| Why the data is rescaled | One neuron at learning rate 0.05 **blows up** on the raw x and y (loss 6e+215) and also when only the mean of x is taken off (5e+144), but settles once x and y are rescaled to mean 0 and spread 1, as AnnaCode does before every fit. With rescaled data the steps are regular: b_hat shrinks by exactly 1 - 2 alpha = 0.8 each step |
| One neuron, `z = m x + b` | gradient descent reaches the closed-form best line (m = 0.050, b = 39.94), but a straight line cannot bend into a V: its typical miss is 24.4, against noise of 2 |
| One neuron with a ReLU, `a = relu(m x + b)` | the chain rule gains one factor, ReLU'(z) = 1 where the neuron is on and 0 where it is off; a point where it is off sends no gradient back (the Excel sheet "ReLU neuron" counts the points that are on) |
| A hidden layer of ReLU neurons | each hidden neuron is a hinge and two can make the V exactly (2 relu(x - 60) + 2 relu(60 - x) = 2\|x - 60\|). A good 2-neuron start misses by 2.04, which is the noise level; 8 neurons by 2.01. Backpropagation is written out one chain-rule step at a time in `ReluNet.gradients` |
| Unlucky starts | from 10 random starts, 0 of 10 one-neuron, **5 of 10 two-neuron**, 6 of 10 three-neuron, 10 of 10 four-neuron and 10 of 10 eight-neuron layers fit the V (loss below 0.05). The failed two-neuron starts ended either flat (a dead neuron, switched on for 0 points) or on one arm (the hinges settled on the same arm, so the other arm's points send no gradient through any neuron). This matches AnnaCode's hint: "Randomize weights and press Train a few times" |
| Overfitting | on 120 fresh points from the same V, the good 2-neuron layer misses by 1.96 (training 2.04) and 8 neurons by 2.02 (training 2.01): no overfitting on this data |
| The learning rate | for the good 2-neuron run, 0.05 is smooth (the loss rose in 10 of 2000 epochs, by at most 0.00415%) and ends at 0.0070; 0.1 is unstable (it rose in 927 epochs, once by 75%) and ends at 0.31 |
| The gradient check | every analytic gradient agrees with finite differences (largest relative difference 6e-10) |
| PyTorch | `loss.backward()` gives the same gradients as the hand derivation (differences of about 1e-16) and `torch.optim.SGD`, with the same gradient clipping, follows the same steps and ends at the same loss |

## Files

```
v_fit.py                  the NumPy fit: rescaling, one neuron, ReLU layers, gradient check, survey, plots, v_fit_results.json
v_fit_torch.py            the same fit in PyTorch, compared with the hand-written gradients
make_v_spreadsheet.py     builds v_fit.xlsx and recalculates it
v_fit.xlsx                Read me | Data | Single neuron | Class layout | ReLU neuron
images/                   the four plots
tests/test_v_fit.py       the checks
```

## The spreadsheet

`Class layout` follows the class page: one column per data point, and for each epoch a block of rows, `guess`, `db = guess - y` and `dm = db x`; the averages of the `dm` and `db` rows give the next m and b. Five epochs of that are the five iterations. `Single neuron` holds the same five iterations as a compact table (loss, both gradients, the new m and b, and the line in the original units) with `SUMPRODUCT`, plus two charts, and a check cell that confirms the two sheets agree. `ReLU neuron` does five iterations for one neuron with a ReLU. The yellow cells (learning rate, starting values) can be changed and everything recalculates. The workbook's numbers equal the Python's to 13 decimals.

## How this relates to AnnaCode's code

AnnaCode's training (`network/training.py`) rescales x and y, starts with small random weights and zero biases, runs a forward pass that keeps what backpropagation needs, computes a delta of 2 x error x f'(pre) at the output, passes errors back layer by layer, averages and clips every gradient to +-5, and steps each weight by its learning rate. The NumPy code here follows that recipe for one hidden layer; it is not a copy of her code.

## Limits

- One fixed draw of the V's random points (AnnaCode draws new ones every time), so the exact numbers change with the points, though the story did not in the tests I tried.
- The surveys of random starts use 10 starts per width, and the validation uses one fresh draw: small experiments.
- The single neuron's start and learning rate (m_hat = 1, b_hat = -1, 0.1), and the ReLU layers' learning rate (0.05) were chosen to make the plots clear, not tuned for the best fit.
