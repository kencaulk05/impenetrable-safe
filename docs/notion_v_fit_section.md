# Part 1: fitting the V with gradient descent (before the lock)

> **Before you publish:** search this section for `[FILL]` and `[CONFIRM]`, then delete this note. The data is AnnaCode's own "V" example, generated the way her code generates it (120 random points, x between 20 and 100, y = 2|x − 60| plus noise of 2); her points are different every time, so mine come from a fixed seed to make every number reproducible. To use points saved from AnnaCode instead, put them in a CSV with columns `x,y` and run `python v_fit.py --data file.csv` and `python make_v_spreadsheet.py --data file.csv`.

Before building the lock I wanted to show that I can find the weights of a model by gradient descent, by hand: one neuron first, then a neuron with a ReLU activation, then a hidden layer of ReLU neurons, which is what AnnaCode needs to fit a V. Everything here is also in the repository as code and as a spreadsheet.

## 1. The data and the goal

AnnaCode's V example is 120 random points with x uniform between 20 and 100 (like a reflection reading) and y = 2|x − 60| plus Gaussian noise of 2: the bottom of the V is at x = 60, and the arms rise by 2 for every unit of x. [FILL: if you fit data you saved from AnnaCode instead, describe it]. The goal is the one from class: find the weights so that the model's output z is close to y, where "close" means a small mean squared error ε.

## 2. One neuron: z = m x + b

A single neuron with no activation is a straight line with two weights, a slope **m** and an intercept **b**. As on the class page, the model's output for point i is z_i = m x_i + b, and the error is

$$\varepsilon=\frac{1}{N}\sum_i\left(y_i-z_i\right)^2=\frac{1}{N}\sum_i\left(y_i-m x_i-b\right)^2$$

**The gradient.** With the chain rule, the derivative of (y_i − m x_i − b)² with respect to m is 2(y_i − m x_i − b)(−x_i), and with respect to b it is 2(y_i − m x_i − b)(−1):

$$\frac{\partial \varepsilon}{\partial m}=-\frac{2}{N}\sum_i\left(y_i-m x_i-b\right)x_i\qquad\qquad \frac{\partial \varepsilon}{\partial b}=-\frac{2}{N}\sum_i\left(y_i-m x_i-b\right)$$

In the spreadsheet each point gets a column, with a row `db = guess − y` (that is −(y − z), the thing inside the sum) and a row `dm = db × x`; the gradients are 2 × the average of those rows. **Gradient descent** moves each weight a small step against its gradient, by an amount set by the learning rate α:

$$m_{new}=m_{old}-\alpha\,\frac{\partial \varepsilon}{\partial m}\qquad\qquad b_{new}=b_{old}-\alpha\,\frac{\partial \varepsilon}{\partial b}$$

**Try it by hand.** Take three points (0, 1), (1, 3), (2, 5) and start at m = 0, b = 0. Then (guess − y) = (−1, −3, −5), so ∂ε/∂m = (2/3)(−1·0 − 3·1 − 5·2) = −26/3 ≈ −8.67 and ∂ε/∂b = (2/3)(−1 − 3 − 5) = −6. Both are negative, so m and b will increase, which is right: the points lie on y = 2x + 1.

**Why the data is rescaled first.** The class page says AnnaCode "normalizes everything to do the fit and then spreads it back out", and the V shows why. I tried one neuron on the V at learning rate 0.05, starting from m = 1, b = 0:

| data | after 40 epochs |
|---|---|
| the raw x and y | **blows up** (loss 6.3e+215) |
| x with its mean taken off | **blows up** (loss 5.0e+144) |
| x and y rescaled to mean 0 and spread 1 | settles (loss 0.998) |

The gradient for m grows with x², and x here runs up to 100, so even a small learning rate makes each step overshoot more than the last. Taking off the mean is not enough on its own because the spread is still large; rescaling makes the mean of x² equal to 1, so the same learning rate is safe. Rescaling is also what makes the five steps below so regular: with x_hat and y_hat at mean 0 and spread 1, b_hat shrinks by a factor 1 − 2α = 0.8 every step exactly, and the gap between m_hat and its final value shrinks by that same factor every step (each step closes 20% of what is left).

**Five iterations on the V** (rescaled start m_hat = 1, b_hat = -1, learning rate α = 0.1; each row is the state after k steps, and these are the rows of the Excel sheets "Single neuron" and "Class layout"). The last two columns turn the same line back into the original units:

| k (steps taken) | m_hat | b_hat | loss | dL/dm | dL/db | m in y per x | b in y |
|---|---|---|---|---|---|---|---|
| 0 | 1.0000 | -1.0000 | 2.8998 | 1.8998 | -2.0000 | 0.9920 | -43.99 |
| 1 | 0.8100 | -0.8000 | 2.2150 | 1.5198 | -1.6000 | 0.8035 | -27.20 |
| 2 | 0.6580 | -0.6400 | 1.7767 | 1.2159 | -1.2800 | 0.6527 | -13.77 |
| 3 | 0.5365 | -0.5120 | 1.4962 | 0.9727 | -1.0240 | 0.5321 | -3.03 |
| 4 | 0.4392 | -0.4096 | 1.3166 | 0.7782 | -0.8192 | 0.4357 | 5.56 |
| 5 | 0.3614 | -0.3277 | 1.2017 |  |  | 0.3585 | 12.44 |

> 🖼️ **INSERT IMAGE 01: `01_first-five-steps.png`**
> The line after 0 to 5 steps: it swings toward the data, and the loss falls from 2.90 to 1.20

**What happens next.** Keep going for 300 epochs and the line settles at m = 0.050, b = 39.94 in the original units. That is exactly the best straight line (the closed-form least-squares answer is m = 0.050, b = 39.94), so gradient descent did its job. But its typical miss is **24.4** while the noise is only 2: **a straight line cannot bend into a V.** The best it can do is a nearly flat line at the average height.

## 3. A ReLU activation

A ReLU is the activation relu(z) = max(0, z): it passes z through when z is positive and outputs 0 otherwise, so it is a hinge. Its derivative is 1 when z > 0 and 0 when z < 0 (AnnaCode uses `pre > 0` for the 1). Without an activation, any number of neurons collapses into one line; the hinge is what lets line segments add up to a V.

**One neuron with a ReLU.** As on the class page: z_i = m x_i + b, a_i = ReLU(z_i), and the loss is L = (1/N) Σ (y_i − a_i)². The chain rule has one more link:

$$\frac{\partial L}{\partial m}=\frac{\partial L}{\partial a}\frac{\partial a}{\partial z}\frac{\partial z}{\partial m}=-\frac{2}{N}\sum_i\left(y_i-a_i\right)\mathrm{ReLU}'(z_i)\,x_i\qquad \frac{\partial L}{\partial b}=-\frac{2}{N}\sum_i\left(y_i-a_i\right)\mathrm{ReLU}'(z_i)$$

The factor ReLU′(z_i) is **1 for points where the neuron is on and 0 where it is off: a point where the neuron is off sends no gradient back.** The Excel sheet "ReLU neuron" runs five iterations of this on the V (it starts at w = 10, c = 0 with 63 of the 120 points switched on and 57 off, and the number that are on grows to 79 as it adapts).

**A hidden layer of ReLU neurons.** AnnaCode's hint for the V is a hidden layer with at least two neurons and ReLU, and a linear output. With H hidden neurons, w_j and c_j the weight and bias of neuron j, and v_j and d the output layer's weights and bias:

$$\hat y=\sum_{j=1}^{H}v_j\,\mathrm{relu}(w_jx+c_j)+d$$

Each hidden neuron makes one hinge, and two hinges can make a V: 2·relu(x − 60) + 2·relu(60 − x) = 2|x − 60| exactly. **Backpropagation** works backwards from the loss, one chain-rule step at a time, with e = ŷ − y, z_j = w_j x + c_j, a_j = relu(z_j):

$$\frac{\partial L}{\partial \hat y}=\frac{2e}{N}\qquad \frac{\partial L}{\partial d}=\sum_i\frac{2e_i}{N}\qquad \frac{\partial L}{\partial v_j}=\sum_i\frac{2e_i}{N}\,a_{ij}$$

$$\frac{\partial L}{\partial z_{ij}}=\frac{2e_i}{N}\,v_j\,\mathbb{1}[z_{ij}>0]\qquad \frac{\partial L}{\partial w_j}=\sum_i\frac{\partial L}{\partial z_{ij}}\,x_i\qquad \frac{\partial L}{\partial c_j}=\sum_i\frac{\partial L}{\partial z_{ij}}$$

This is what AnnaCode's `network/training.py` does, written for any number of layers: a forward pass that keeps each layer's inputs and pre- and post-activation values; a delta at the output of 2·error·f′(pre); for each layer going backwards, a weight gradient of delta × the input it saw, a bias gradient equal to the delta, and an error passed back to the previous layer as delta × weight, multiplied by that layer's f′(pre); then every gradient is averaged over the points, clipped to ±5, and used for the step weight ← weight − α·gradient. My code below does the same for one hidden layer.

> 🖼️ **INSERT IMAGE 02: `02_two-hinges.png`**
> The fitted two-neuron layer: each dashed line is one hidden neuron (flat where it is switched off), and their sum is the V

> 🖼️ **INSERT IMAGE 03: `03_data-and-fit.png`**
> Anna's V, the one-neuron line, and the ReLU layers: a line cannot bend, a ReLU layer can

**Width.** One hidden neuron makes one hinge, so at best it follows one arm: its typical miss is 19.8. Two neurons from a good start fit the V: a typical miss of **2.04**, which is the noise level (σ = 2). Eight neurons: 2.01.

**Why a start can be unlucky.** AnnaCode starts with small random weights and zero biases, so every hinge starts bent at the middle of the data, and where it ends up depends on the random start (her hint says to "Randomize weights and press Train a few times"). I trained each width from 10 random starts and counted how many fit the V (loss below 0.05):

| hidden neurons | starts out of 10 that fit the V |
|---|---|
| 1 | 0 |
| 2 | 5 |
| 3 | 6 |
| 4 | 10 |
| 8 | 10 |

The 5 two-neuron starts that failed were of two kinds. **1 ended flat** (loss ≈ 1.0, no better than the average): one neuron was pushed off for every point (switched on for 0 points, so no gradient reaches it: the "dead ReLU") and the other became almost constant. **4 ended on one arm** (loss 0.66 to 0.73, switched on for only 30, 44, 29, 45 of the 120 points): the hinges that were still switched on settled on the same arm, so the points of the other arm are switched off for every neuron and push no gradient through any of them, and the other arm can never be learned. More neurons made the fit more **reliable**: 4 neurons fit the V in 10 of 10 starts and 8 in 10 of 10.

**Is the wider layer just memorising the noise?** I tested on 120 fresh points from the same V that no layer trained on. The typical miss on them was 1.96 for the good 2-neuron layer (2.04 on its training points) and 2.02 for 8 neurons (2.01 on training), so on this data the extra width did not overfit. The straight line missed by 22.3 on fresh points too.

> 🖼️ **INSERT IMAGE 04: `04_loss.png`**
> Loss against epoch: the line and the one-armed fits level off high; the ReLU layers that fit the V keep falling until they reach the noise

**The learning rate.** For the same good 2-neuron run: α = 0.02: the loss never rose and ended at 0.0073; α = 0.05: the loss rose in 10 of 2000 epochs, by at most 0.00415% and ended at 0.0070; α = 0.1: the loss rose in 927 of 2000 epochs, by at most 75.5% and ended at 0.3075; α = 0.4: the loss rose in 4 of 2000 epochs, by at most 390% and ended at 0.7305. So 0.05 worked and 0.1 already did not: a bigger step overshoots whenever a hinge slides past a data point, because the loss of a ReLU network has kinks. The plots use α = 0.05.

**The same fit on AnnaCode's own site.** I also did this on AnnaCode itself (Fitting, example "V"): a hidden layer of three neurons with a ReLU, an output layer with no activation (the screen shows two linear neurons in a row, which collapse into a single line, the class page's point), learning rate 0.05, and I pressed Randomize weights and Train several times until it fit, as its hint says. The screen shows a loss of 0.007 and "120 points · average miss 2.0", which is the noise level; my NumPy fit of the same kind of data gets a loss of 0.0070 and an average miss of 2.04. The weights it shows (in the original units) put the three hinges at about x = 53, 63 and 63, from the rounded numbers on the screen. Needing several tries is the unlucky-start problem above. [CONFIRM: these numbers are read from my screenshot]

> 🖼️ **INSERT IMAGE 05: `05_annacode-v-fit.png`**
> My fit on AnnaCode's site: three ReLU neurons, loss 0.007, average miss 2.0

## 4. The Excel spreadsheet

**Attach `v_fit.xlsx` here.** [FILL: attach the file] It follows the class page's layout. **Class layout** puts one column on each of the 120 data points, and for each epoch a block of rows: `guess`, `db = guess − y` and `dm = db × x`; the averages of the `dm` and `db` rows give the next m and b. Five epochs of that are the five iterations. **Single neuron** holds the same five iterations as a compact table (loss, both gradients, the new m and b, and the same line in the original units), computed with `SUMPRODUCT` instead of a column per point, plus two charts (the line moving toward the data, and the loss falling); a check cell confirms the two sheets agree. **ReLU neuron** does the five iterations for one neuron with a ReLU and counts the points that are switched on. **Data** holds the numbers and the rescaling, and **Read me** has the math, the colour legend and every assumption. Every iteration number is a live formula, so changing a yellow cell (learning rate, starting values) recalculates everything; the numbers equal the Python's to 13 decimals.

## 5. The Python code

*Every snippet is copied from the repository (`v_fit.py`, `v_fit_torch.py`).* The gradients of the single neuron:

```python
def linear_gradients(x, y, m, b):
    """L = mean (m x + b - y)^2   so   dL/dm = 2 mean(e x)   and   dL/db = 2 mean(e)   where e = m x + b - y."""
    e = m * x + b - y
    return 2.0 * np.mean(e * x), 2.0 * np.mean(e)
```

Gradient descent on it:

```python
def train_linear(x, y, m=M0, b=B0, lr=LR_LINEAR, epochs=EPOCHS, stop_if_blown_up=False):
    hist = {"m": [m], "b": [b], "loss": [linear_loss(x, y, m, b)], "dm": [], "db": []}
    with np.errstate(over="ignore", invalid="ignore"):
        for _ in range(epochs):
            dm, db = linear_gradients(x, y, m, b)
            m, b = m - lr * dm, b - lr * db                      # step downhill
            hist["dm"].append(dm); hist["db"].append(db)
            hist["m"].append(m); hist["b"].append(b); hist["loss"].append(linear_loss(x, y, m, b))
            if stop_if_blown_up and not np.isfinite(hist["loss"][-1]):
                break
    return hist
```

The ReLU layer: the forward pass, backpropagation written out (the comments are the chain rule above), and the step with AnnaCode's gradient clipping:

```python
class ReluNet:
    """One hidden layer of H ReLU neurons, then a weighted sum:   y_hat = sum_j v_j relu(w_j x + c_j) + d.
    Starts like AnnaCode: small random weights, uniform in +-1/sqrt(fan_in), and zero biases."""

    def __init__(self, H, seed=1):
        r = np.random.default_rng(seed)
        self.w = r.uniform(-1.0, 1.0, H)                         # hidden layer: one input each, so fan_in = 1
        self.c = np.zeros(H)
        self.v = r.uniform(-1.0, 1.0, H) / np.sqrt(H)            # output layer: fan_in = H
        self.d = 0.0

    def forward(self, x):
        z = np.outer(x, self.w) + self.c                         # (N, H): the pre-activations
        a = np.maximum(z, 0.0)                                   # ReLU
        return z, a, a @ self.v + self.d

    def loss(self, x, y):
        return float(np.mean((self.forward(x)[2] - y) ** 2))

    def gradients(self, x, y):
        """Backpropagation, one chain-rule step at a time.
        e = y_hat - y                          L = mean e^2          dL/dy_hat = 2e/N
        y_hat = sum v_j a_j + d                dL/dd = sum 2e/N      dL/dv_j = sum (2e/N) a_j
        a_j = relu(z_j)                        dL/dz_j = (2e/N) v_j 1[z_j > 0]    (the ReLU passes the gradient only where it is on)
        z_j = w_j x + c_j                      dL/dw_j = sum dL/dz_j x             dL/dc_j = sum dL/dz_j"""
        N = len(x)
        z, a, yhat = self.forward(x)
        dyhat = 2.0 * (yhat - y) / N
        dz = dyhat[:, None] * self.v[None, :] * (z > 0)
        return {"w": (dz * x[:, None]).sum(axis=0), "c": dz.sum(axis=0), "v": (dyhat[:, None] * a).sum(axis=0), "d": dyhat.sum()}

    def step(self, g, lr):
        clip = lambda v: np.clip(v, -MAX_GRAD, MAX_GRAD)         # AnnaCode clips each gradient to +-5
        self.w -= lr * clip(g["w"]); self.c -= lr * clip(g["c"]); self.v -= lr * clip(g["v"]); self.d -= lr * float(clip(g["d"]))
```

And the check that the derivation is right: the analytic gradient against finite differences, for every weight:

```python
def gradient_check(x, y, H=3, seed=1, eps=1e-6):
    """The analytic gradients against (L(p + eps) - L(p - eps)) / 2 eps for every single parameter. Returns the largest relative difference."""
    net = ReluNet(H, seed)
    net.c = np.random.default_rng(seed + 7).normal(0, 0.3, H)    # nonzero biases, so the check does not sit on the kinks
    g = net.gradients(x, y)
    worst = 0.0
    for name in ("w", "c", "v"):
        arr = getattr(net, name)
        for j in range(H):
            keep = arr[j]
            arr[j] = keep + eps; up = net.loss(x, y)
            arr[j] = keep - eps; down = net.loss(x, y)
            arr[j] = keep
            num = (up - down) / (2 * eps)
            worst = max(worst, abs(num - g[name][j]) / max(1e-9, abs(num) + abs(g[name][j])))
    keep = net.d
    net.d = keep + eps; up = net.loss(x, y); net.d = keep - eps; down = net.loss(x, y); net.d = keep
    num = (up - down) / (2 * eps)
    return max(worst, abs(num - g["d"]) / max(1e-9, abs(num) + abs(g["d"])))


def on_counts(net, x):
    """For each hidden neuron: for how many of the points it is switched on (z > 0). A neuron that is on for 0 points is dead: no gradient passes through it."""
    return [int(c) for c in ((np.outer(x, net.w) + net.c) > 0).sum(axis=0)]
```

The largest relative difference was 6.1e-10.

## 6. PyTorch finds the same gradients

The same fit in PyTorch (`v_fit_torch.py`): `loss.backward()` applies the chain rule automatically.

```python
def autograd_linear(x, y, m, b):
    xt, yt = torch.tensor(x), torch.tensor(y)
    mt, bt = torch.tensor(m, requires_grad=True), torch.tensor(b, requires_grad=True)
    loss = ((mt * xt + bt - yt) ** 2).mean()
    loss.backward()                                    # backpropagation: the chain rule, applied for us
    return mt.grad.item(), bt.grad.item()
```

| Check | Largest difference |
|---|---|
| single neuron: loss.backward() against my dL/dm and dL/db | 0.0e+00 |
| ReLU layer (3 neurons): loss.backward() against my backpropagation, every weight | 5.6e-17 |
| five steps of torch.optim.SGD against my gradient descent on m and b | 8.9e-16 |
| final loss after 2000 epochs, good 2-neuron ReLU layer: by hand against torch.optim.SGD (with the same clipping) | 0.00696591 against 0.00696591 |

So what PyTorch does when it trains a network is what I did here: a forward pass, a loss, a backward pass that gives every weight's gradient, and a small step downhill. The lock's network will have many more weights and will be built from convolutions and pooling, but the learning is this same recipe.

## Images to upload (in the order they appear)

| # | File | Where | What it shows |
|---|---|---|---|
| 01 | `01_first-five-steps.png` | Section 2: One neuron | the line after 0 to 5 steps of gradient descent (the Excel rows) |
| 02 | `02_two-hinges.png` | Section 3: A ReLU activation | the two hidden neurons and their sum |
| 03 | `03_data-and-fit.png` | Section 3: A ReLU activation | Anna's V with the one-neuron line and the ReLU-layer fits |
| 04 | `04_loss.png` | Section 3: A ReLU activation | loss against epoch for every model |
| 05 | `05_annacode-v-fit.png` | Section 3: A ReLU activation | your own screenshot of the V fit on AnnaCode's site: three ReLU neurons, loss 0.007, average miss 2.0 |
