# Stratégie complète : Market Making + Microprice + Ornstein-Uhlenbeck

La stratégie est un **market making mean-reverting** où le prix de référence n’est pas le mid-price, mais le **microprice**, puis un processus d’Ornstein-Uhlenbeck est appliqué sur ce microprice.

---

## 1. Données de marché utilisées

À chaque instant, on récupère dans le carnet :

$$
b_t = \text{best bid}
$$

$$
a_t = \text{best ask}
$$

$$
V^b_t = \text{volume au best bid}
$$

$$
V^a_t = \text{volume au best ask}
$$

Le best bid $b_t$ est le meilleur prix auquel on peut vendre immédiatement.

Le best ask $a_t$ est le meilleur prix auquel on peut acheter immédiatement.

---

## 2. Calcul du microprice

On calcule le microprice :

$$
M_t =
\frac{a_t V^b_t + b_t V^a_t}{V^b_t + V^a_t}
$$

Le microprice donne une meilleure estimation du prix court terme que le mid-price, car il intègre le déséquilibre du carnet.

Si le bid est très chargé, le microprice monte vers l’ask.

Si l’ask est très chargé, le microprice baisse vers le bid.

---

## 3. Modèle OU appliqué au microprice

On suppose que le microprice suit un processus d’Ornstein-Uhlenbeck :

$$
dM_t = \kappa(\mu - M_t)dt + \sigma dW_t
$$

avec :

$$
\mu = \text{moyenne long terme du microprice}
$$

$$
\kappa = \text{vitesse de retour à la moyenne}
$$

$$
\sigma = \text{volatilité du microprice}
$$

---

## 4. Fair price

Le fair price est la prévision OU du microprice à horizon $h$ :

$$
F_t(h) =
\mu + e^{-\kappa h}(M_t - \mu)
$$

Donc :

$$
\boxed{
\text{fair price} = \text{prévision mean-reverting du microprice}
}
$$

Si le microprice est sous la moyenne, le fair price sera au-dessus du microprice.

Si le microprice est au-dessus de la moyenne, le fair price sera en dessous du microprice.

---

## 5. Signal directionnel

Le signal est :

$$
\alpha_t = F_t(h) - M_t
$$

Si :

$$
\alpha_t > 0
$$

le modèle anticipe une hausse, donc on veut être plutôt long.

Si :

$$
\alpha_t < 0
$$

le modèle anticipe une baisse, donc on veut être plutôt short.

---

## 6. Inventaire cible

On transforme l’écart à la moyenne en inventaire cible.

D’abord, on calcule le z-score :

$$
z_t =
\frac{M_t - \mu}{\sigma / \sqrt{2\kappa}}
$$

Puis :

$$
q_t^\star =
- Q_{\max}\tanh(\eta z_t)
$$

avec :

$$
Q_{\max} = \text{inventaire maximal autorisé}
$$

$$
\eta = \text{agressivité de l’inventaire}
$$

Résultat :

Si :

$$
M_t < \mu
$$

alors :

$$
q_t^\star > 0
$$

on veut être long.

Si :

$$
M_t > \mu
$$

alors :

$$
q_t^\star < 0
$$

on veut être short.

Si :

$$
M_t \approx \mu
$$

alors :

$$
q_t^\star \approx 0
$$

on veut être quasiment neutre.

---

## 7. Prix de réservation

On modifie Avellaneda-Stoikov pour ne pas revenir vers zéro inventaire, mais vers l’inventaire cible $q_t^\star$.

Le prix de réservation est :

$$
r_t =
F_t(h)
-
\gamma
\frac{\sigma^2}{2\kappa}
(1 - e^{-2\kappa h})
(q_t - q_t^\star)
$$

avec :

$$
q_t = \text{inventaire actuel}
$$

$$
\gamma = \text{aversion au risque d’inventaire}
$$

Si l’inventaire actuel est trop bas par rapport à la cible, le prix de réservation monte : on devient plus agressif à l’achat.

Si l’inventaire actuel est trop haut par rapport à la cible, le prix de réservation baisse : on devient plus agressif à la vente.

---

## 8. Quotes maker

On place les ordres maker autour du prix de réservation :

$$
p_t^{bid} = r_t - \delta_t
$$

$$
p_t^{ask} = r_t + \delta_t
$$

où $\delta_t$ est le demi-spread de cotation.

Pour rester maker :

$$
p_t^{bid} \leq b_t
$$

$$
p_t^{ask} \geq a_t
$$

Si on veut acheter plus, on rapproche le bid du best bid.

Si on veut vendre plus, on rapproche l’ask du best ask.

---

## 9. Ordres taker

S’il n’y a pas de frais ni d’adverse selection, la règle taker est simple.

On achète taker si :

$$
F_t(h) > a_t
$$

et si :

$$
q_t < q_t^\star
$$

On vend taker si :

$$
F_t(h) < b_t
$$

et si :

$$
q_t > q_t^\star
$$

Donc on prend la liquidité uniquement lorsque le fair price estimé est meilleur que le prix disponible dans le carnet.

---

## 10. Taille des ordres

On base la taille des ordres sur l’écart entre l’inventaire cible et l’inventaire actuel :

$$
D_t = q_t^\star - q_t
$$

Si :

$$
D_t > 0
$$

on veut acheter.

Si :

$$
D_t < 0
$$

on veut vendre.

On peut donc augmenter la taille au bid quand on veut acheter, et augmenter la taille à l’ask quand on veut vendre.

Une forme simple :

$$
L_t^{bid}
=
L_0
\left[
1 + \theta \frac{q_t^\star - q_t}{Q_{\max}}
\right]_+
$$

$$
L_t^{ask}
=
L_0
\left[
1 - \theta \frac{q_t^\star - q_t}{Q_{\max}}
\right]_+
$$

avec :

$$
L_0 = \text{taille de base}
$$

$$
\theta = \text{agressivité sur la taille}
$$

et :

$$
[x]_+ = \max(x, 0)
$$

---

## 11. Logique finale

La stratégie complète est :

$$
\boxed{
\text{carnet}
\rightarrow
\text{microprice}
\rightarrow
\text{OU}
\rightarrow
\text{fair price}
\rightarrow
\text{inventaire cible}
\rightarrow
\text{prix de réservation}
\rightarrow
\text{quotes maker/taker}
}
$$

En version très synthétique :

1. On calcule le **microprice** à partir du carnet.
2. On applique un **processus OU** au microprice.
3. On obtient un **fair price mean-reverting**.
4. On définit un **inventaire cible** : long sous la moyenne, short au-dessus.
5. On calcule un **prix de réservation** qui pousse l’inventaire vers cette cible.
6. On place les **ordres maker** autour de ce prix.
7. On utilise les **ordres taker** seulement si le fair price dépasse directement le best ask ou le best bid.
8. On ajuste les tailles selon l’écart entre l’inventaire actuel et l’inventaire cible.

La phrase qui résume tout :

$$
\boxed{
\text{Market making autour d’un fair price OU du microprice, avec un inventaire cible mean-reverting.}
}
$$
