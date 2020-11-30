## Bias detection using Deep Supervised Contrastive Learning (Goodfellas)
#### [[Project Website]](https://ghafeleb.github.io/goodfellas/)


[Sina Aghaei](mailto:saghaei@usc.edu)<sup>1</sup>, [Zahra Abrishami](mailto:zabrisha@usc.edu)<sup>2</sup>, 
[Ali Ghafelehbash](mailto:ghafeleb@usc.edu)<sup>1</sup>, [Bahareh Harandizadeh](mailto:harandiz@usc.edu)<sup>2</sup>, [Negar Mokhberian](mailto:nmokhber@usc.edu)<sup>2</sup>

<sup>1</sup>Department of Industrial and Systems Engineering, University of Southern California, Los Angeles, CA 9008<br/>
<sup>2</sup>Department of Computer Science, University of Southern California, Los Angeles, CA 9008


## Abstract
In this paper, we propose an end-to-end model to detect ideological bias in news articles. We propose a deep supervised contrastive learning model to learn new representations for text with the goal of separating the embeddings from different classes to expose the bias in the textual data and exploit this bias to identify political orientation of different news articles.

## Introduction

In any nation, media can be a dividing issue as it might reflect topics differently based on the political views or ideological lines. Understanding this implicit bias is becoming more and more critical, specifically by growing numbers of social media and news agencies platforms. Recently the number of research in this domain also is increasing, from detection and mitigation of gender bias[[1]](#1), to polarization detection in political views[[4]](#4) also ideological bias of News[[6]](#6). We think the analysis of bias in the news could be very helpful for the readers as make them more responsible about what they hear or read. 

In this work we want to understand how different are news articles on the same subject but from different political parties (left and right) from each other. We want to detect the potential political bias within news articles. We, as human, can easily identify the different political orientation of articles from opposite parties. For example, how different conservative news agencies such as ''Fox News'' approach a subject like Covid-19 compares to a liberal news agency such as ''CNN''. The question is that can machines detect this political bias as well?
%
A proxy for this goal could be a classifier which tries to classify news articles depending on their political party. Existing approaches such as[[6]](#6) tackle this problem using a classifier on the space of the words embedding. The problem with this approach is that it is not end to end, i.e., the embedding are not trained with the purpose of getting a good classification result. As we can see in figure~\ref{fig:bias-embedding}(right), with general purpose word embedding models such as BERT[[5]](#5), classifying embedded articles might not be straightforward. Having a new representation such as the one shown in figure~\ref{fig:bias-embedding}(left) where it maximizes the distance between embedding from different classes could make the classification task much easier, as in the latent space, the bias is exposed.


<p float="center">
  <img src="https://github.com/ghafeleb/goodfellas/blob/main/docs/resources/embedding.PNG" width="450" /> 
  <img src="https://github.com/ghafeleb/goodfellas/blob/main/docs/resources/bias.PNG" width="450" />
</p>
<p align="center">
<b>Figure 1:</b> An ideal latent space (left) where the articles from opposite classes are far from each other which helps to expose the political bias (right) and improves the performance of the classification task.
</p>







To achieve such representation for news articles we propose a modification to the deep contrastive Learning model for unsupervised textual representation introduced in~\cite{giorgi2020declutr}. In~\cite{giorgi2020declutr}, they have a unsupervised contrastive loss which for any given textual segment (aka anchor span) it minimizes the distance between its embedding and the embeddings of other textual segments randomly sampled from nearby in the same document (aka positive spans). It also maximizes the distance between the given anchor from other spans which are not in its neighborhood (aka negative spans). In their model, the positive and negative spans are not chosen according to the label of the documents. We propose to alter their objective to a supervised contrastive loss so that the negative spans are sampled from articles with opposite label. The motivation is to maximize the distance between articles from different classes.



## Problem Formulation
We consider a setting where we have various documents (articles) from two different parties called \emph{liberal} (label being 0) and \emph{conservative} (label being 1). All the documents are about a similar topic, \newsa{Covid-19}.

We sample a batch of $N$ documents from the \emph{liberal} party (class label being 0) and $N$ documents from the \emph{conservative} party (class label being 1). For each document from class $k \in \{0,1\}$ we sample $A$ anchor spans $s^k_i,~ i \in \{1,\dots,AN\}$ and per anchor we sample $P$ positive spans $s^k_{i+pAN},~ p \in \{1,\dots,P\}$ following the procedure introduced in~\cite{giorgi2020declutr}. \ali{Isn't it better to have $s_{i, j}^k$ such that $i \in \{1, 2, ..., N\}$ and $j \in \{1, 2, ..., A\}$?}

Given an input span, $s^k_i$, a ''transformer-based language models'' encoder $f$, maps each token in the input span $s^k_i$ to a word embedding.
    
Similar to~\cite{giorgi2020declutr}, a pooler $g(.)$, maps the encoded anchor spans $f(s^k_i)$ to a fixed length embedding $g(f(s^k_i))$. \ali{Is it possible to impose fixed length of output to our embedder?}
    
We take the average of the positive spans per anchor as follows
    $$e^k_{i+AN} = \frac{1}{P}\sum_{p=1}^{P}g(f(s^k_{i+pAN}))$$
    
<p align="center">
  <img src="https://github.com/ghafeleb/goodfellas/blob/main/docs/resources/AvgPosSpan.PNG" width="450" /> 
</p>

Now we have $2(AN)$ datapoints per party and in total $4(AN)$ datapoints per batch. \zahra{How did we get these numbers?} We define our supervised contrastive loss function as follows

<p align="center">
  <img src="https://github.com/ghafeleb/goodfellas/blob/main/docs/resources/Loss1.PNG" width="450" /> 
</p>
<br>
<p align="center">
  <img src="https://github.com/ghafeleb/goodfellas/blob/main/docs/resources/Loss2.PNG" width="450" /> 
</p>

where

<p align="center">
  <img src="https://github.com/ghafeleb/goodfellas/blob/main/docs/resources/Loss3.PNG" width="450" /> 
</p>


\ali{What is "sim" in the formulation?, what is $\tau$?} Loss function~\eqref{eq:loss_k} enforces anchor $e^k_i$ to be as closes as possible to its corresponding positive span $e^k_{i+AN}$ (which is referred to as easy positive) and at the same time to be as far as possible from all spans $e^{1-k}_m$ from the opposite party, i.e., for any given anchor from class $k$, the corresponding set of negative spans only include the spans from opposite class $1-k$ (which are referred to as easy negative). Figure~\ref{fig:model} visualizes a simplified overview of our model. \ali{Are we using hard positive or hard negative in our project? If no, I think we should remove the term "easy".}
\zahra{What is m? Does it refer to all documents from the different parties?}

<p align="center">
  <img src="https://github.com/ghafeleb/goodfellas/blob/main/docs/resources/model.PNG" width="450" /> 
</p>
<p align="center">
<b>Figure 2:</b> Overview of the supervised contrastive objective. In this figure, we show a simplified example where in each batch we sample 1 document $d^k$ per class $k$ and we sample 1 anchor span $e^k_i$ per document and 1 positive span $e^k_j$ per anchor. All the spans are fed through the same encoder $f$ and pooler $g$ to produce the corresponding embedding vectors $e^k_i$ and $e^k_j$. The model is trained to minimize the distance between each anchor $e^k_i$ and its corresponding positive $e^k_j$ and maximize the distance between anchor $e^k_i$ and all other spans from class $1-k$. \ali{I think we shouk}
</p>
<p align="center">
  <img src="https://github.com/ghafeleb/goodfellas/blob/main/docs/resources/data_head.png" width="900" /> 
</p align="center">
<p  align="center">
<b>Figure 3:</b> Overview of the dataset.
</p>


<p align="center">
  <img src="https://github.com/ghafeleb/goodfellas/blob/main/docs/resources/length_distribution.png" width="450" /> 
</p>
<p  align="center">
<b>Figure 3:</b> Overview of the dataset.
</p>


## Data
For our experiments we use AYLIEN’s Coronavirus news dataset\footnote{\url{https://aylien.com/blog/coronavirus-news-dashboard}} (Global COVID related news since Jan 2020). This dataset contains numerous news articles from different news sources with different political orientations. For simplicity we only focus on news articles from two news sources Huffington Post, which is considered as liberal (class $0$), and Breitbart which is considered as conservative (class $1$).

In the figure~\ref{fig:data_head} we show the first few lines of the dataset. We assign Huffington's articles class $0$ and Breitbart's articles class $1$. Another important observation from the data is the distribution of the length (number of words) of the articles which is shown in figure~\ref{fig:data_head}. This is important to the step where we sample the anchor-positive pairs from the data. 

<p align="center">
  <img src="https://github.com/ghafeleb/goodfellas/blob/main/docs/resources/data_head.png" width="900" /> 
</p align="center">
<p  align="center">
<b>Figure 3:</b> Overview of the dataset.
</p>

<p align="center">
  <img src="https://github.com/ghafeleb/goodfellas/blob/main/docs/resources/length_distribution.png" width="450" /> 
</p>
<p  align="center">
<b>Figure 3:</b> Overview of the dataset.
</p>

Another step that we do is topic modeling to make sure all the articles are about the same subject ''covid19''. We use Latent Dirichlet Allocation (LDA) for this step. The topics we found are as follows:

- huffpost people new time home like 19 covid pandemic health help year just
- trump president donald people house states white pandemic news state virus americans health going huffpost
- minister china chinese cases italy wuhan government confirmed border reported countries virus prime authorities deaths
- hanks rita kimmel jimmy wilson cordero aniston kloots fallon elvis song tom actor conan corden
- newstex al views content et https advice www accuracy commentary authoritative guarantees distributors huffington conferring



## References
<a id="1">[1]</a> 
Lucas Dixon, John Li, Jeffrey Sorensen, Nithum Thain, and Lucy Vasserman. Measuring and mitigating unintended bias in text classification. In proceedings of the 2018AAAI/ACM Conference on AI, Ethics, and Society, pages 67–73, 2018

<a id="4">[4]</a> 
Jon Green, Jared Edgerton, Daniel Naftel, Kelsey Shoub, and Skyler J. Cranmer. Elusiveconsensus:  Polarization in elite communication on the COVID-19 pandemic. Science Advances, 6(28):eabc2717, July 2020

<a id="6">[6]</a> 
Negar Mokhberian, Andrés Abeliuk, Patrick Cummings, and Kristina Lerman. Moralframing and ideological bias of news.arXiv preprint arXiv:2009.12979, 2020.

<a id="5">[5]</a> 
Tomas Mikolov, Ilya Sutskever, Kai Chen, Greg S Corrado, and Jeff Dean. Distributed representations of words and phrases and their compositionality. In advances in neural information processing systems, pages 3111–3119, 2013


## Bias detection using Deep Supervised Contrastive Learning (Goodfellas)

You can use the [editor on GitHub](https://github.com/ghafeleb/goodfellas.github.io/edit/gh-pages/index.md) to maintain and preview the content for your website in Markdown files.

Whenever you commit to this repository, GitHub Pages will run [Jekyll](https://jekyllrb.com/) to rebuild the pages in your site, from the content in your Markdown files.

### Markdown

Markdown is a lightweight and easy-to-use syntax for styling your writing. It includes conventions for

```markdown
Syntax highlighted code block

# Header 1
## Header 2
### Header 3

- Bulleted
- List

1. Numbered
2. List

**Bold** and _Italic_ and `Code` text

[Link](url) and ![Image](src)
```

For more details see [GitHub Flavored Markdown](https://guides.github.com/features/mastering-markdown/).

### Jekyll Themes

Your Pages site will use the layout and styles from the Jekyll theme you have selected in your [repository settings](https://github.com/ghafeleb/goodfellas.github.io/settings). The name of this theme is saved in the Jekyll `_config.yml` configuration file.

### Support or Contact

Having trouble with Pages? Check out our [documentation](https://docs.github.com/categories/github-pages-basics/) or [contact support](https://github.com/contact) and we’ll help you sort it out.
